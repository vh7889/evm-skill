import argparse

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="单钱包查询 ERC20 代币余额")
    parser.add_argument("--address", required=True, help="钱包地址")
    parser.add_argument("--token", required=True, help="ERC20 合约地址")
    parser.add_argument("--rpc", required=True, help="RPC 地址")
    parser.add_argument("--token-decimals", type=int, help="代币 decimals，不填则链上读取")
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
    web3 = Web3(Web3.HTTPProvider(args.rpc))
    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    print(f"rpc_connected={web3.is_connected()}")
    if not web3.is_connected():
        raise RuntimeError("RPC 连接失败")

    addr = Web3.to_checksum_address(args.address)
    token_addr = Web3.to_checksum_address(args.token)
    token = web3.eth.contract(address=token_addr, abi=ERC20_ABI)

    decimals = args.token_decimals
    if decimals is None:
        decimals = int(token.functions.decimals().call())
    bal_raw = int(token.functions.balanceOf(addr).call())
    bal = str(bal_raw / (10**decimals))

    print(f"address={addr}")
    print(f"token={token_addr}")
    print(f"decimals={decimals}")
    print(f"balance={bal}")
    print(f"balance_raw={bal_raw}")


if __name__ == "__main__":
    main()
