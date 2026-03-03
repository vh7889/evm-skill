import argparse
from decimal import Decimal

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="单钱包调用闭源合约")
    parser.add_argument("--private-key", required=True, help="调用钱包私钥")
    parser.add_argument("--contract", required=True, help="目标合约地址")
    parser.add_argument("--data", required=True, help="16进制 calldata，例如 0x1234...")
    parser.add_argument("--rpc", required=True, help="RPC 地址")
    parser.add_argument("--value", default="0", help="可选，附带原生币数量（人类可读），默认 0")
    parser.add_argument("--receipt-timeout", type=int, default=180, help="回执超时秒数")
    parser.add_argument(
        "--gas-price-gwei",
        type=float,
        help="可选，手动指定 gasPrice（gwei）；不填则自动读取链上实时 gasPrice",
    )
    args = parser.parse_args()

    if not Web3.is_address(args.contract):
        raise ValueError("contract 地址非法")
    if not args.data.startswith("0x"):
        raise ValueError("data 必须是 0x 开头的 16 进制")
    body = args.data[2:]
    if len(body) % 2 != 0:
        raise ValueError("data 16 进制长度必须是偶数")
    int(body or "0", 16)
    if Decimal(args.value) < 0:
        raise ValueError("value 必须 >= 0")
    return args


def main() -> None:
    args = parse_args()
    web3 = Web3(Web3.HTTPProvider(args.rpc))
    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    print(f"rpc_connected={web3.is_connected()}")
    if not web3.is_connected():
        raise RuntimeError("RPC 连接失败")

    account = web3.eth.account.from_key(args.private_key)
    from_addr = account.address
    contract_addr = Web3.to_checksum_address(args.contract)
    chain_id = web3.eth.chain_id
    nonce = web3.eth.get_transaction_count(from_addr, "pending")
    value_wei = int(web3.to_wei(Decimal(args.value), "ether"))

    tx = {
        "chainId": chain_id,
        "from": from_addr,
        "to": contract_addr,
        "value": value_wei,
        "data": args.data,
        "nonce": nonce,
    }
    tx["gas"] = int(web3.eth.estimate_gas(tx) * 1.2)
    if args.gas_price_gwei is not None:
        tx["gasPrice"] = int(web3.to_wei(Decimal(str(args.gas_price_gwei)), "gwei"))
    else:
        tx["gasPrice"] = int(web3.eth.gas_price)

    signed = account.sign_transaction(tx)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction).hex()
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=args.receipt_timeout)

    print(f"from={from_addr}")
    print(f"contract={contract_addr}")
    print(f"value={args.value}")
    print(f"gas_price_gwei={tx['gasPrice'] / 1e9}")
    print(f"tx_hash={tx_hash}")
    print(f"status={int(receipt.status)}")


if __name__ == "__main__":
    main()
