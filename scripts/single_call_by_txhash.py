import argparse
import json
import os
from datetime import datetime
from decimal import Decimal

from web3 import Web3

from rpc_resilient import ResilientRPC, add_rpc_resilience_args


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="通过 tx hash 查询 to/value/data，并导出可编辑参数文件"
    )
    parser.add_argument("--tx-hash", required=True, help="链上交易哈希")
    parser.add_argument("--rpc", required=True, help="RPC 地址")
    parser.add_argument("--output", help="可选，导出 JSON 文件路径")
    add_rpc_resilience_args(parser)
    args = parser.parse_args()
    if not args.tx_hash.startswith("0x") or len(args.tx_hash) != 66:
        raise ValueError("tx-hash 格式非法")
    return args


def main() -> None:
    args = parse_args()
    rpc = ResilientRPC(
        primary_rpc=args.rpc,
        backup_rpcs=args.rpc_backup,
        timeout=args.rpc_timeout,
        max_retries=args.rpc_max_retries,
        backoff_base=args.rpc_backoff_base,
    )
    print(f"rpc_connected={rpc.ensure_connected()}")
    print(f"rpc_current={rpc.current_rpc}")

    tx = rpc.call(lambda w3: w3.eth.get_transaction(args.tx_hash))
    if tx.get("to") is None:
        raise RuntimeError("该交易是合约创建交易（to=null），无法提取普通调用参数")

    to_addr = Web3.to_checksum_address(tx["to"])
    value_wei = int(tx.get("value", 0))
    data_hex = tx.get("input", "0x")
    if isinstance(data_hex, bytes):
        data_hex = data_hex.hex()
        if not data_hex.startswith("0x"):
            data_hex = "0x" + data_hex

    print(f"source_tx={args.tx_hash}")
    print(f"to={to_addr}")
    print(f"value_wei={value_wei}")
    print(f"value={Decimal(value_wei) / (Decimal(10) ** 18)}")
    print(f"data={data_hex}")

    out_obj = {
        "sourceTxHash": args.tx_hash,
        "rpc": rpc.current_rpc,
        "to": to_addr,
        "valueWei": str(value_wei),
        "data": data_hex,
    }

    if args.output:
        output_path = args.output
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_hash = args.tx_hash[2:10]
        output_path = f"output/log/tx_params_{ts}-{short_hash}.json"

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out_obj, f, ensure_ascii=False, indent=2)

    print(f"output_json={output_path}")


if __name__ == "__main__":
    main()
