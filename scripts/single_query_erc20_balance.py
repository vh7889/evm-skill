import argparse

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
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="单钱包查询 ERC20 代币余额")
    parser.add_argument("--address", required=True, help="钱包地址")
    parser.add_argument("--token", required=True, help="ERC20 合约地址")
    parser.add_argument("--rpc", required=True, help="RPC 地址")
    parser.add_argument("--token-decimals", type=int, help="代币 decimals，不填则链上读取")
    add_rpc_resilience_args(parser)
    args = parser.parse_args()
    if not Web3.is_address(args.address):
        raise ValueError("address 非法")
    if not Web3.is_address(args.token):
        raise ValueError("token 地址非法")
    if args.token_decimals is not None and args.token_decimals < 0:
        raise ValueError("token-decimals 必须 >= 0")
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
    token_addr = Web3.to_checksum_address(args.token)
    token = rpc.call(lambda w3: w3.eth.contract(address=token_addr, abi=ERC20_ABI))

    decimals = args.token_decimals
    if decimals is None:
        decimals = int(rpc.call(lambda _w3: token.functions.decimals().call()))
    bal_raw = int(rpc.call(lambda _w3: token.functions.balanceOf(addr).call()))
    bal = str(bal_raw / (10**decimals))

    print(f"address={addr}")
    print(f"token={token_addr}")
    print(f"decimals={decimals}")
    print(f"balance={bal}")
    print(f"balance_wei={bal_raw}")


if __name__ == "__main__":
    main()
