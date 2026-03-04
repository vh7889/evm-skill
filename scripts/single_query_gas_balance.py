import argparse

from web3 import Web3

from rpc_resilient import ResilientRPC, add_rpc_resilience_args


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="单钱包查询原生 Gas 代币余额")
    parser.add_argument("--address", required=True, help="钱包地址")
    parser.add_argument("--rpc", required=True, help="RPC 地址")
    add_rpc_resilience_args(parser)
    args = parser.parse_args()
    if not Web3.is_address(args.address):
        raise ValueError("address 非法")
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
    if not rpc.ensure_connected():
        raise RuntimeError("RPC 连接失败")

    addr = Web3.to_checksum_address(args.address)
    bal_wei = int(rpc.call(lambda w3: w3.eth.get_balance(addr)))
    bal = str(rpc.call(lambda w3: w3.from_wei(bal_wei, "ether")))

    print(f"address={addr}")
    print(f"balance={bal}")
    print(f"balance_wei={bal_wei}")


if __name__ == "__main__":
    main()
