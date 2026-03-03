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
]

HEADERS = [
    "序号",
    "钱包地址",
    "Token",
    "余额",
    "余额Raw",
    "状态",
    "失败原因",
    "时间",
]


def now_text() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量查询 ERC20 代币余额")
    parser.add_argument("--wallet-csv", required=True, help="钱包 CSV 文件")
    parser.add_argument("--token", required=True, help="ERC20 合约地址")
    parser.add_argument("--rpc", required=True, help="RPC 地址")
    parser.add_argument("--threads", required=True, type=int, help="线程数量")
    parser.add_argument("--token-decimals", type=int, help="代币 decimals，不填则链上读取")
    parser.add_argument(
        "--mode",
        default="all",
        choices=["all", "failed", "pending"],
        help="all=处理全部，failed=仅处理失败，pending=仅处理未开始",
    )
    parser.add_argument("--output-csv", help="输出结果 CSV 路径（默认 output/log）")
    args = parser.parse_args()
    if args.threads < 1:
        raise ValueError("threads 必须 >= 1")
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
            address_field = None
            for name in ["address", "Address", "钱包地址", "接收地址", "转出地址"]:
                if name in reader.fieldnames:
                    address_field = name
                    break
            if address_field:
                for i, row in enumerate(reader, start=1):
                    addr = (row.get(address_field) or "").strip()
                    if addr:
                        wallets.append({"序号": str(i), "钱包地址": addr})
                return wallets

    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader, start=1):
            if len(row) < 2:
                continue
            addr = (row[1] or "").strip()
            if addr and addr != "address":
                wallets.append({"序号": str(i), "钱包地址": addr})
    return wallets


def write_output(output_csv: Path, rows: List[Dict[str, str]], lock: threading.Lock) -> None:
    with lock:
        tmp = output_csv.with_suffix(output_csv.suffix + ".tmp")
        with tmp.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=HEADERS)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        tmp.replace(output_csv)


def load_or_init_output(output_csv: Path, wallets: List[Dict[str, str]], token_addr: str) -> List[Dict[str, str]]:
    if output_csv.exists():
        rows: List[Dict[str, str]] = []
        with output_csv.open("r", newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({k: row.get(k, "") for k in HEADERS})
        existing = {r.get("钱包地址", "").lower(): r for r in rows if r.get("钱包地址")}
        for w in wallets:
            key = w["钱包地址"].lower()
            if key not in existing:
                rows.append(
                    {
                        "序号": w["序号"],
                        "钱包地址": w["钱包地址"],
                        "Token": token_addr,
                        "余额": "",
                        "余额Raw": "",
                        "状态": "PENDING",
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
                "钱包地址": w["钱包地址"],
                "Token": token_addr,
                "余额": "",
                "余额Raw": "",
                "状态": "PENDING",
                "失败原因": "",
                "时间": "",
            }
        )
    return rows


def select_rows(rows: List[Dict[str, str]], mode: str) -> List[Dict[str, str]]:
    selected = []
    for row in rows:
        status = (row.get("状态") or "PENDING").upper()
        if mode == "failed" and status == "FAILED":
            selected.append(row)
        elif mode == "pending" and status in ("PENDING", ""):
            selected.append(row)
        elif mode == "all":
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

    token_addr = Web3.to_checksum_address(args.token)
    token = web3.eth.contract(address=token_addr, abi=ERC20_ABI)
    decimals = args.token_decimals
    if decimals is None:
        decimals = int(token.functions.decimals().call())

    if args.output_csv:
        output_csv = Path(args.output_csv).resolve()
    else:
        out_dir = Path("output/log").resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        output_csv = out_dir / f"{wallet_csv.stem}_erc20_balance_query.csv"
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    wallets = load_wallets(wallet_csv)
    if not wallets:
        raise ValueError("钱包 CSV 中没有可用地址")

    rows = load_or_init_output(output_csv, wallets, token_addr)
    file_lock = threading.Lock()
    write_output(output_csv, rows, file_lock)

    targets = select_rows(rows, args.mode)
    print(f"token={token_addr} decimals={decimals}")
    print(f"output_file={output_csv}")
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
        addr_raw = (row.get("钱包地址") or "").strip()
        if not Web3.is_address(addr_raw):
            row["状态"] = "FAILED"
            row["失败原因"] = "非法地址"
            row["时间"] = now_text()
            write_output(output_csv, rows, file_lock)
            return
        try:
            addr = Web3.to_checksum_address(addr_raw)
            balance_raw = int(token.functions.balanceOf(addr).call())
            balance = str(balance_raw / (10**decimals))
            row["Token"] = token_addr
            row["余额Raw"] = str(balance_raw)
            row["余额"] = balance
            row["状态"] = "SUCCESS"
            row["失败原因"] = ""
            row["时间"] = now_text()
            write_output(output_csv, rows, file_lock)
        except Exception as e:  # noqa: BLE001
            row["状态"] = "FAILED"
            row["失败原因"] = str(e)
            row["时间"] = now_text()
            write_output(output_csv, rows, file_lock)

    with ThreadPoolExecutor(max_workers=args.threads) as ex:
        futures = [ex.submit(process_row, row) for row in targets if not stop_event.is_set()]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as e:  # noqa: BLE001
                print(f"worker_error={e}")

    success = sum(1 for r in rows if (r.get("状态") or "").upper() == "SUCCESS")
    failed = sum(1 for r in rows if (r.get("状态") or "").upper() == "FAILED")
    pending = sum(1 for r in rows if (r.get("状态") or "").upper() in ("PENDING", ""))
    print(f"done success={success} failed={failed} pending={pending}")
    print(f"output_file={output_csv}")


if __name__ == "__main__":
    main()
