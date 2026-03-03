import argparse
import csv
import datetime
import signal
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from pathlib import Path
from typing import Dict, List

from web3 import Web3

from rpc_resilient import ResilientRPC, add_rpc_resilience_args


ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
]

HEADERS = [
    "序号",
    "转出地址",
    "接收地址",
    "归集数量",
    "归集数量Base",
    "状态",
    "成功哈希",
    "失败原因",
    "时间",
]


def now_text() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量归集 ERC20 代币")
    parser.add_argument("--main-address", required=True, help="主钱包地址（接收地址）")
    parser.add_argument("--wallet-csv", required=True, help="分发钱包 CSV（需包含私钥）")
    parser.add_argument("--token", required=True, help="ERC20 合约地址")
    parser.add_argument("--rpc", required=True, help="RPC 地址")
    parser.add_argument("--threads", required=True, type=int, help="线程数量")
    parser.add_argument("--token-decimals", type=int, help="代币 decimals，不填则链上读取")
    parser.add_argument(
        "--mode",
        default="all",
        choices=["all", "failed", "pending"],
        help="all=处理未成功钱包，failed=仅处理失败，pending=仅处理未开始",
    )
    parser.add_argument("--log-csv", help="归集日志 CSV 路径（默认自动生成固定名）")
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
    if not Web3.is_address(args.main_address):
        raise ValueError("main-address 非法")
    if not Web3.is_address(args.token):
        raise ValueError("token 地址非法")
    if args.token_decimals is not None and args.token_decimals < 0:
        raise ValueError("token-decimals 必须 >= 0")
    return args


def load_wallets(csv_path: Path) -> List[Dict[str, str]]:
    wallets: List[Dict[str, str]] = []
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames:
            addr_field = None
            pk_field = None
            for name in ["address", "Address", "钱包地址", "转出地址"]:
                if name in reader.fieldnames:
                    addr_field = name
                    break
            for name in ["privateKey", "private_key", "私钥"]:
                if name in reader.fieldnames:
                    pk_field = name
                    break
            if addr_field and pk_field:
                for i, row in enumerate(reader, start=1):
                    addr = (row.get(addr_field) or "").strip()
                    pk = (row.get(pk_field) or "").strip()
                    if addr and pk:
                        wallets.append({"序号": str(i), "转出地址": addr, "privateKey": pk})
                return wallets

    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader, start=1):
            if len(row) < 3:
                continue
            addr = (row[1] or "").strip()
            pk = (row[2] or "").strip()
            if addr and pk and addr != "address":
                wallets.append({"序号": str(i), "转出地址": addr, "privateKey": pk})
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
    log_csv: Path, wallets: List[Dict[str, str]], main_address: str
) -> List[Dict[str, str]]:
    if log_csv.exists():
        rows: List[Dict[str, str]] = []
        with log_csv.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({k: row.get(k, "") for k in HEADERS})

        existing = {r.get("转出地址", "").lower(): r for r in rows if r.get("转出地址")}
        for w in wallets:
            key = w["转出地址"].lower()
            if key not in existing:
                rows.append(
                    {
                        "序号": w["序号"],
                        "转出地址": w["转出地址"],
                        "接收地址": main_address,
                        "归集数量": "",
                        "归集数量Base": "",
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
                "转出地址": w["转出地址"],
                "接收地址": main_address,
                "归集数量": "",
                "归集数量Base": "",
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

    chain_id = int(rpc.call(lambda w3: w3.eth.chain_id))
    main_address = Web3.to_checksum_address(args.main_address)
    token_addr = Web3.to_checksum_address(args.token)
    token = rpc.call(lambda w3: w3.eth.contract(address=token_addr, abi=ERC20_ABI))

    decimals = args.token_decimals
    if decimals is None:
        decimals = int(rpc.call(lambda _w3: token.functions.decimals().call()))
    if decimals < 0:
        raise ValueError("decimals 非法")

    print(f"main_address={main_address}")
    print(f"chain_id={chain_id}")
    print(f"token={token_addr} decimals={decimals}")

    if args.log_csv:
        log_csv = Path(args.log_csv).resolve()
    else:
        log_dir = Path("output/log").resolve()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_csv = log_dir / f"{wallet_csv.stem}_erc20_collect_log.csv"
    log_csv.parent.mkdir(parents=True, exist_ok=True)

    wallets = load_wallets(wallet_csv)
    if not wallets:
        raise ValueError("钱包 CSV 中没有可用地址+私钥")

    pk_map = {w["转出地址"].lower(): w["privateKey"] for w in wallets}
    rows = load_or_init_log(log_csv, wallets, main_address)
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

    def process_row(row: Dict[str, str]) -> None:
        if stop_event.is_set():
            return

        from_raw = (row.get("转出地址") or "").strip()
        pk = pk_map.get(from_raw.lower(), "")
        if not pk:
            row["状态"] = "FAILED"
            row["失败原因"] = "缺少私钥"
            row["时间"] = now_text()
            write_log(log_csv, rows, file_lock)
            return
        if not Web3.is_address(from_raw):
            row["状态"] = "FAILED"
            row["失败原因"] = "非法转出地址"
            row["时间"] = now_text()
            write_log(log_csv, rows, file_lock)
            return

        account = rpc.call(lambda w3: w3.eth.account.from_key(pk))
        from_addr = Web3.to_checksum_address(from_raw)
        if account.address.lower() != from_addr.lower():
            row["状态"] = "FAILED"
            row["失败原因"] = "私钥与地址不匹配"
            row["时间"] = now_text()
            write_log(log_csv, rows, file_lock)
            return

        row["状态"] = "IN_PROGRESS"
        row["接收地址"] = main_address
        row["成功哈希"] = ""
        row["失败原因"] = ""
        row["时间"] = now_text()
        write_log(log_csv, rows, file_lock)

        try:
            nonce = int(rpc.call(lambda w3: w3.eth.get_transaction_count(from_addr, "pending")))
            balance = int(rpc.call(lambda _w3: token.functions.balanceOf(from_addr).call()))
            if balance <= 0:
                row["状态"] = "FAILED"
                row["失败原因"] = "token 余额为 0"
                row["时间"] = now_text()
                write_log(log_csv, rows, file_lock)
                return

            tx = token.functions.transfer(main_address, balance).build_transaction(
                {
                    "chainId": chain_id,
                    "from": from_addr,
                    "nonce": nonce,
                }
            )
            if "gas" not in tx or not tx["gas"]:
                tx["gas"] = int(rpc.call(lambda w3: w3.eth.estimate_gas(tx)) * 1.2)

            if args.gas_price_gwei is not None:
                tx["gasPrice"] = int(rpc.call(lambda w3: w3.to_wei(Decimal(str(args.gas_price_gwei)), "gwei")))
            else:
                tx["gasPrice"] = int(rpc.call(lambda w3: w3.eth.gas_price))

            signed = account.sign_transaction(tx)
            tx_hash = rpc.call(lambda w3: w3.eth.send_raw_transaction(signed.raw_transaction).hex())
            receipt = rpc.call(
                lambda w3: w3.eth.wait_for_transaction_receipt(tx_hash, timeout=args.receipt_timeout)
            )

            row["归集数量Base"] = str(balance)
            row["归集数量"] = str(Decimal(balance) / (Decimal(10) ** decimals))
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
