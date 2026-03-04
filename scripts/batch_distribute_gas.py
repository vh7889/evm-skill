import argparse
import csv
import datetime
import random
import signal
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from pathlib import Path
from typing import Dict, List

from web3 import Web3

from rpc_resilient import ResilientRPC, add_rpc_resilience_args


HEADERS = [
    "序号",
    "转出地址",
    "接收地址",
    "分发数量",
    "分发数量Wei",
    "状态",
    "成功哈希",
    "失败原因",
    "时间",
]


def now_text() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量分发 Gas 代币（原生币）")
    parser.add_argument("--main-private-key", required=True, help="主钱包私钥")
    parser.add_argument("--wallet-csv", required=True, help="分发钱包 CSV 文件")
    parser.add_argument("--rpc", required=True, help="RPC 地址")
    parser.add_argument("--threads", required=True, type=int, help="线程数量")
    parser.add_argument(
        "--mode",
        default="all",
        choices=["all", "failed", "pending"],
        help="all=处理未成功的钱包，failed=仅处理失败，pending=仅处理未开始",
    )
    parser.add_argument("--amount", help="固定数量，例如 0.002")
    parser.add_argument("--amount-min", help="范围最小值，例如 0.001")
    parser.add_argument("--amount-max", help="范围最大值，例如 0.003")
    parser.add_argument("--log-csv", help="转账日志 CSV 路径（默认自动生成固定名）")
    parser.add_argument("--receipt-timeout", type=int, default=180, help="回执超时秒数")
    parser.add_argument(
        "--gas-price-gwei",
        type=float,
        help="可选，手动指定 gasPrice（gwei）；不填则自动读取链上实时 gasPrice",
    )
    add_rpc_resilience_args(parser)
    args = parser.parse_args()

    if args.threads < 1:
        raise ValueError("threads 必须 >= 1")

    has_fixed = args.amount is not None
    has_range = args.amount_min is not None or args.amount_max is not None
    if has_fixed and has_range:
        raise ValueError("固定数量和范围数量只能二选一")
    if not has_fixed and not (args.amount_min and args.amount_max):
        raise ValueError("必须提供 --amount，或同时提供 --amount-min 与 --amount-max")

    if args.amount_min and args.amount_max:
        if Decimal(args.amount_min) <= 0 or Decimal(args.amount_max) <= 0:
            raise ValueError("范围数量必须 > 0")
        if Decimal(args.amount_min) > Decimal(args.amount_max):
            raise ValueError("amount-min 不能大于 amount-max")
    if args.amount is not None and Decimal(args.amount) <= 0:
        raise ValueError("amount 必须 > 0")

    return args


def pick_amount(args: argparse.Namespace) -> Decimal:
    if args.amount is not None:
        return Decimal(args.amount)
    low = Decimal(args.amount_min)
    high = Decimal(args.amount_max)
    if low == high:
        return low
    ratio = Decimal(str(random.random()))
    value = low + (high - low) * ratio
    return value.quantize(Decimal("0.000000000000000001"))


def load_wallets(csv_path: Path) -> List[Dict[str, str]]:
    wallets: List[Dict[str, str]] = []
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames:
            address_field = None
            for name in ["address", "Address", "钱包地址", "接收地址"]:
                if name in reader.fieldnames:
                    address_field = name
                    break
            if address_field:
                for i, row in enumerate(reader, start=1):
                    addr = (row.get(address_field) or "").strip()
                    if addr:
                        wallets.append({"序号": str(i), "接收地址": addr})
                return wallets

    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader, start=1):
            if len(row) < 2:
                continue
            addr = (row[1] or "").strip()
            if addr and addr != "address":
                wallets.append({"序号": str(i), "接收地址": addr})
    return wallets


def write_log(log_csv: Path, rows: List[Dict[str, str]], lock: threading.Lock) -> None:
    with lock:
        tmp = log_csv.with_suffix(log_csv.suffix + ".tmp")
        with tmp.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=HEADERS)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        tmp.replace(log_csv)


def load_or_init_log(
    log_csv: Path, wallets: List[Dict[str, str]], from_addr: str
) -> List[Dict[str, str]]:
    if log_csv.exists():
        rows: List[Dict[str, str]] = []
        with log_csv.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                fixed = {k: row.get(k, "") for k in HEADERS}
                rows.append(fixed)
        existing = {r["接收地址"].lower(): r for r in rows if r.get("接收地址")}
        for w in wallets:
            key = w["接收地址"].lower()
            if key not in existing:
                rows.append(
                    {
                        "序号": w["序号"],
                        "转出地址": from_addr,
                        "接收地址": w["接收地址"],
                        "分发数量": "",
                        "分发数量Wei": "",
                        "状态": "PENDING",
                        "成功哈希": "",
                        "失败原因": "",
                        "时间": "",
                    }
                )
        return rows

    rows = []
    for w in wallets:
        rows.append(
            {
                "序号": w["序号"],
                "转出地址": from_addr,
                "接收地址": w["接收地址"],
                "分发数量": "",
                "分发数量Wei": "",
                "状态": "PENDING",
                "成功哈希": "",
                "失败原因": "",
                "时间": "",
            }
        )
    return rows


def select_rows(rows: List[Dict[str, str]], mode: str) -> List[Dict[str, str]]:
    selected: List[Dict[str, str]] = []
    for row in rows:
        status = (row.get("状态") or "PENDING").upper()
        if mode == "failed" and status == "FAILED":
            selected.append(row)
        elif mode == "pending" and status in ("PENDING", ""):
            selected.append(row)
        elif mode == "all" and status != "SUCCESS":
            selected.append(row)
    return selected


def main() -> None:
    args = parse_args()
    wallet_csv = Path(args.wallet_csv).resolve()
    if not wallet_csv.exists():
        raise FileNotFoundError(f"wallet csv 不存在: {wallet_csv}")

    rpc = ResilientRPC(
        primary_rpc=args.rpc,
        backup_rpcs=args.rpc_backup,
        timeout=args.rpc_timeout,
        max_retries=args.rpc_max_retries,
        backoff_base=args.rpc_backoff_base,
    )
    print(f"rpc_connected={rpc.ensure_connected()}")
    print(f"rpc_current={rpc.current_rpc}")
    if not rpc.ensure_connected():
        raise RuntimeError("RPC 连接失败")

    account = rpc.call(lambda w3: w3.eth.account.from_key(args.main_private_key))
    from_addr = account.address
    chain_id = int(rpc.call(lambda w3: w3.eth.chain_id))
    print(f"from={from_addr}")
    print(f"chain_id={chain_id}")

    if args.log_csv:
        log_csv = Path(args.log_csv).resolve()
    else:
        log_dir = Path("output/log").resolve()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_csv = log_dir / f"{wallet_csv.stem}_gas_distribution_log.csv"
    log_csv.parent.mkdir(parents=True, exist_ok=True)

    wallets = load_wallets(wallet_csv)
    if not wallets:
        raise ValueError("钱包 CSV 中没有可用地址")

    rows = load_or_init_log(log_csv, wallets, from_addr)
    file_lock = threading.Lock()
    write_log(log_csv, rows, file_lock)

    targets = select_rows(rows, args.mode)
    print(f"log_file={log_csv}")
    print(f"total_wallets={len(rows)} target_wallets={len(targets)} mode={args.mode}")
    if not targets:
        return

    stop_event = threading.Event()

    def stop_handler(signum, frame):  # noqa: ARG001
        stop_event.set()
        print("\n收到中断信号，停止领取新任务，正在收尾已开始任务...")

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    nonce_lock = threading.Lock()
    nonce_cursor = int(rpc.call(lambda w3: w3.eth.get_transaction_count(from_addr, "pending")))
    print(f"start_nonce={nonce_cursor}")

    def next_nonce() -> int:
        nonlocal nonce_cursor
        with nonce_lock:
            n = nonce_cursor
            nonce_cursor += 1
            return n

    def process_row(row: Dict[str, str]) -> None:
        if stop_event.is_set():
            return

        to_addr_raw = (row.get("接收地址") or "").strip()
        if not Web3.is_address(to_addr_raw):
            row["状态"] = "FAILED"
            row["失败原因"] = "非法地址"
            row["时间"] = now_text()
            write_log(log_csv, rows, file_lock)
            return

        to_addr = Web3.to_checksum_address(to_addr_raw)
        amount_native = pick_amount(args)
        amount_wei = int(rpc.call(lambda w3: w3.to_wei(amount_native, "ether")))
        nonce = next_nonce()

        row["转出地址"] = from_addr
        row["接收地址"] = to_addr
        row["分发数量"] = str(amount_native)
        row["分发数量Wei"] = str(amount_wei)
        row["状态"] = "IN_PROGRESS"
        row["成功哈希"] = ""
        row["失败原因"] = ""
        row["时间"] = now_text()
        write_log(log_csv, rows, file_lock)

        try:
            tx = {
                "chainId": chain_id,
                "from": from_addr,
                "to": to_addr,
                "value": amount_wei,
                "nonce": nonce,
                "gas": 21000,
            }
            if args.gas_price_gwei is not None:
                tx["gasPrice"] = int(rpc.call(lambda w3: w3.to_wei(Decimal(str(args.gas_price_gwei)), "gwei")))
            else:
                tx["gasPrice"] = int(rpc.call(lambda w3: w3.eth.gas_price))

            signed = account.sign_transaction(tx)
            tx_hash = rpc.call(lambda w3: w3.eth.send_raw_transaction(signed.raw_transaction).hex())

            receipt = rpc.call(
                lambda w3: w3.eth.wait_for_transaction_receipt(tx_hash, timeout=args.receipt_timeout)
            )
            row["成功哈希"] = tx_hash
            row["时间"] = now_text()
            if int(receipt.status) == 1:
                row["状态"] = "SUCCESS"
                row["失败原因"] = ""
            else:
                row["状态"] = "FAILED"
                row["失败原因"] = "receipt status=0"
            write_log(log_csv, rows, file_lock)
        except Exception as e:  # noqa: BLE001
            row["状态"] = "FAILED"
            row["失败原因"] = str(e)
            row["时间"] = now_text()
            write_log(log_csv, rows, file_lock)

    with ThreadPoolExecutor(max_workers=args.threads) as ex:
        futures = []
        for row in targets:
            if stop_event.is_set():
                break
            futures.append(ex.submit(process_row, row))

        for f in as_completed(futures):
            try:
                f.result()
            except Exception as e:  # noqa: BLE001
                print(f"worker_error={e}")

    success = sum(1 for r in rows if (r.get("状态") or "").upper() == "SUCCESS")
    failed = sum(1 for r in rows if (r.get("状态") or "").upper() == "FAILED")
    pending = sum(
        1 for r in rows if (r.get("状态") or "").upper() in ("PENDING", "IN_PROGRESS", "")
    )
    print(f"done success={success} failed={failed} pending_or_inprogress={pending}")
    print(f"log_file={log_csv}")


if __name__ == "__main__":
    main()
