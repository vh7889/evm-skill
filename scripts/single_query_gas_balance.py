import argparse

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="单钱包查询原生 Gas 代币余额")
    parser.add_argument("--address", required=True, help="钱包地址")
    parser.add_argument("--rpc", required=True, help="RPC 地址")
    args = parser.parse_args()
    if not Web3.is_address(args.address):
        raise ValueError("address 非法")
    return args


def main() -> None:
    args = parse_args()
    web3 = Web3(Web3.HTTPProvider(args.rpc))
    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    print(f"rpc_connected={web3.is_connected()}")
    if not web3.is_connected():
        raise RuntimeError("RPC 连接失败")

    addr = Web3.to_checksum_address(args.address)
    bal_wei = int(web3.eth.get_balance(addr))
    bal = str(web3.from_wei(bal_wei, "ether"))

    print(f"address={addr}")
    print(f"balance={bal}")
    print(f"balance_wei={bal_wei}")


if __name__ == "__main__":
    main()
