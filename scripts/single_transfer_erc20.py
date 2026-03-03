import argparse
from decimal import Decimal

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="单钱包一对一转 ERC20 代币")
    parser.add_argument("--private-key", required=True, help="转出钱包私钥")
    parser.add_argument("--to", required=True, help="接收地址")
    parser.add_argument("--token", required=True, help="ERC20 合约地址")
    parser.add_argument("--amount", required=True, help="数量（人类可读，例如 0.1）")
    parser.add_argument("--rpc", required=True, help="RPC 地址")
    parser.add_argument("--token-decimals", type=int, help="代币 decimals，不填则链上读取")
    parser.add_argument("--receipt-timeout", type=int, default=180, help="回执超时秒数")
    parser.add_argument(
        "--gas-price-gwei",
        type=float,
        help="可选，手动指定 gasPrice（gwei）；不填则自动读取链上实时 gasPrice",
    )
    args = parser.parse_args()
    if Decimal(args.amount) <= 0:
        raise ValueError("amount 必须 > 0")
    if not Web3.is_address(args.to):
        raise ValueError("to 地址非法")
    if not Web3.is_address(args.token):
        raise ValueError("token 地址非法")
    if args.token_decimals is not None and args.token_decimals < 0:
        raise ValueError("token-decimals 必须 >= 0")
    return args


def to_base_units(amount: Decimal, decimals: int) -> int:
    scaled = amount * (Decimal(10) ** decimals)
    if scaled != scaled.to_integral_value():
        raise ValueError("数量精度超过 token decimals")
    value = int(scaled)
    if value <= 0:
        raise ValueError("数量必须 > 0")
    return value


def main() -> None:
    args = parse_args()
    web3 = Web3(Web3.HTTPProvider(args.rpc))
    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    print(f"rpc_connected={web3.is_connected()}")
    if not web3.is_connected():
        raise RuntimeError("RPC 连接失败")

    account = web3.eth.account.from_key(args.private_key)
    from_addr = account.address
    to_addr = Web3.to_checksum_address(args.to)
    token_addr = Web3.to_checksum_address(args.token)
    token = web3.eth.contract(address=token_addr, abi=ERC20_ABI)

    decimals = args.token_decimals
    if decimals is None:
        decimals = int(token.functions.decimals().call())
    amount_base = to_base_units(Decimal(args.amount), decimals)

    chain_id = web3.eth.chain_id
    nonce = web3.eth.get_transaction_count(from_addr, "pending")

    tx = token.functions.transfer(to_addr, amount_base).build_transaction(
        {"chainId": chain_id, "from": from_addr, "nonce": nonce}
    )
    if "gas" not in tx or not tx["gas"]:
        tx["gas"] = int(web3.eth.estimate_gas(tx) * 1.2)
    if args.gas_price_gwei is not None:
        tx["gasPrice"] = int(web3.to_wei(Decimal(str(args.gas_price_gwei)), "gwei"))
    else:
        tx["gasPrice"] = int(web3.eth.gas_price)

    signed = account.sign_transaction(tx)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction).hex()
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=args.receipt_timeout)

    print(f"from={from_addr}")
    print(f"to={to_addr}")
    print(f"token={token_addr}")
    print(f"amount={args.amount}")
    print(f"amount_base={amount_base}")
    print(f"gas_price_gwei={tx['gasPrice'] / 1e9}")
    print(f"tx_hash={tx_hash}")
    print(f"status={int(receipt.status)}")


if __name__ == "__main__":
    main()
