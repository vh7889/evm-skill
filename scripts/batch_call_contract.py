import argparse
import csv
import datetime
import signal
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware


HEADERS = [
    "序号",
    "转出地址",
    "接收地址",
    "调用数据",
    "状态",
    "成功哈希",
    "失败原因",
    "时间",
]


def now_text() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量闭源合约调用")
    parser.add_argument("--wallet-csv", required=True, help="分发钱包 CSV（需包含私钥）")
    parser.add_argument("--rpc", required=True, help="RPC 地址")
    parser.add_argument("--threads", required=True, type=int, help="线程数量")
    parser.add_argument("--data", required=True, help="16进制 calldata，例如 0x1234...")
    parser.add_argument("--contract", required=True, help="目标合约地址")
    parser.add_argument(
        "--mode",
        default="all",
        choices=["all", "failed", "pending"],
        help="all=处理未成功钱包，failed=仅处理失败，pending=仅处理未开始",
    )
    parser.add_argument("--log-csv", help="调用日志 CSV 路径（默认自动生成固定名）")
    parser.add_argument("--receipt-timeout", type=int, default=180, help="回执超时秒数")
    parser.add_argument(
        "--gas-price-gwei",
        type=float,
        help="可选，手动指定 gasPrice（gwei）；不填则自动读取链上实时 gasPrice",
    )
    args = parser.parse_args()

    if args.threads < 1:
        raise ValueError("threads 必须 >= 1")
    if not Web3.is_address(args.contract):
        raise ValueError("contract 地址非法")
    if not args.data.startswith("0x"):
        raise ValueError("data 必须是 0x 开头的 16 进制")
    hex_body = args.data[2:]
    if len(hex_body) % 2 != 0:
        raise ValueError("data 16 进制长度必须是偶数")
    int(hex_body or "0", 16)
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
    log_csv: Path, wallets: List[Dict[str, str]], contract_addr: str, data_hex: str
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
                        "接收地址": contract_addr,
                        "调用数据": data_hex,
                        "状态": "PENDING",
                        "成功哈希": "",
                        "失败原因": "",
                        "时间": "",
                    }
                )
        return rows

    rows: List[Dict[str, str]] = []
    for w in wallets:
        rows.append(
            {
                "序号": w["序号"],
                "转出地址": w["转出地址"],
                "接收地址": contract_addr,
                "调用数据": data_hex,
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

    web3 = Web3(Web3.HTTPProvider(args.rpc))
    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    print(f"rpc_connected={web3.is_connected()}")
    if not web3.is_connected():
        raise RuntimeError("RPC 连接失败")

    contract_addr = Web3.to_checksum_address(args.contract)
    chain_id = web3.eth.chain_id
    print(f"chain_id={chain_id}")
    print(f"contract={contract_addr}")

    if args.log_csv:
        log_csv = Path(args.log_csv).resolve()
    else:
        log_dir = Path("output/log").resolve()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_csv = log_dir / f"{wallet_csv.stem}_contract_call_log.csv"
    log_csv.parent.mkdir(parents=True, exist_ok=True)

    wallets = load_wallets(wallet_csv)
    if not wallets:
        raise ValueError("钱包 CSV 中没有可用地址+私钥")

    pk_map = {w["转出地址"].lower(): w["privateKey"] for w in wallets}
    rows = load_or_init_log(log_csv, wallets, contract_addr, args.data)
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

        account = web3.eth.account.from_key(pk)
        from_addr = Web3.to_checksum_address(from_raw)
        if account.address.lower() != from_addr.lower():
            row["状态"] = "FAILED"
            row["失败原因"] = "私钥与地址不匹配"
            row["时间"] = now_text()
            write_log(log_csv, rows, file_lock)
            return

        row["状态"] = "IN_PROGRESS"
        row["接收地址"] = contract_addr
        row["调用数据"] = args.data
        row["成功哈希"] = ""
        row["失败原因"] = ""
        row["时间"] = now_text()
        write_log(log_csv, rows, file_lock)

        try:
            nonce = web3.eth.get_transaction_count(from_addr, "pending")
            tx = {
                "chainId": chain_id,
                "from": from_addr,
                "to": contract_addr,
                "value": 0,
                "data": args.data,
                "nonce": nonce,
            }
            estimated = web3.eth.estimate_gas(tx)
            tx["gas"] = int(estimated * 1.2)

            if args.gas_price_gwei is not None:
                tx["gasPrice"] = int(web3.to_wei(args.gas_price_gwei, "gwei"))
            else:
                tx["gasPrice"] = int(web3.eth.gas_price)

            signed = account.sign_transaction(tx)
            tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction).hex()
            receipt = web3.eth.wait_for_transaction_receipt(
                tx_hash, timeout=args.receipt_timeout
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
