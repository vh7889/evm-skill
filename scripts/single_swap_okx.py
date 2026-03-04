import argparse
import json
import time
from decimal import Decimal
from typing import Any, Dict

from web3 import Web3

from okx_api_client import OkxApiClient
from rpc_resilient import ResilientRPC, add_rpc_resilience_args


def parse_int(v: Any, default: int = 0) -> int:
    if v is None:
        return default
    if isinstance(v, int):
        return v
    s = str(v).strip()
    if not s:
        return default
    if s.startswith("0x") or s.startswith("0X"):
        return int(s, 16)
    if "." in s:
        return int(Decimal(s))
    return int(s)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="单钱包 OKX Swap（quote -> swap -> simulate -> broadcast）")
    parser.add_argument("--private-key", required=True, help="钱包私钥")
    parser.add_argument("--rpc", required=True, help="RPC 地址（用于 nonce/签名）")
    parser.add_argument("--chain-index", default="56", help="OKX chainIndex，默认 56(BSC)")
    parser.add_argument("--from-token", required=True, help="from token 地址，原生币用 0xeeee...eeee")
    parser.add_argument("--to-token", required=True, help="to token 地址，原生币用 0xeeee...eeee")
    parser.add_argument("--amount-wei", required=True, help="输入数量（最小单位）")
    parser.add_argument("--swap-mode", default="exactIn", choices=["exactIn", "exactOut"], help="默认 exactIn")
    parser.add_argument("--slippage-percent", default="1", help="滑点百分比，默认 1")
    parser.add_argument("--poll-seconds", type=int, default=2, help="查询订单状态前等待秒数")
    add_rpc_resilience_args(parser)
    args = parser.parse_args()
    if parse_int(args.amount_wei, 0) <= 0:
        raise ValueError("amount-wei 必须 > 0")
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
    if not rpc.ensure_connected():
        raise RuntimeError("RPC 连接失败")

    account = rpc.call(lambda w3: w3.eth.account.from_key(args.private_key))
    from_addr = account.address
    chain_id = int(rpc.call(lambda w3: w3.eth.chain_id))
    nonce = int(rpc.call(lambda w3: w3.eth.get_transaction_count(from_addr, "pending")))
    client = OkxApiClient()

    quote = client.get(
        "/api/v6/dex/aggregator/quote",
        {
            "chainIndex": str(args.chain_index),
            "fromTokenAddress": args.from_token,
            "toTokenAddress": args.to_token,
            "amount": str(args.amount_wei),
            "swapMode": args.swap_mode,
        },
    )

    swap = client.get(
        "/api/v6/dex/aggregator/swap",
        {
            "chainIndex": str(args.chain_index),
            "fromTokenAddress": args.from_token,
            "toTokenAddress": args.to_token,
            "amount": str(args.amount_wei),
            "slippagePercent": str(args.slippage_percent),
            "userWalletAddress": from_addr,
            "swapMode": args.swap_mode,
        },
    )

    swap_resp = swap.get("response") or {}
    if str(swap_resp.get("code")) != "0":
        print(json.dumps({"quote": quote, "swap": swap}, ensure_ascii=False))
        return
    swap_data = swap_resp.get("data") or []
    if not swap_data:
        print(json.dumps({"quote": quote, "swap": swap}, ensure_ascii=False))
        return

    tx_obj = (swap_data[0] or {}).get("tx") or {}
    tx_to = tx_obj.get("to")
    tx_data = tx_obj.get("data")
    tx_value = parse_int(tx_obj.get("value"), 0)
    tx_gas = parse_int(tx_obj.get("gas"), 300_000)
    tx_gas_price = parse_int(tx_obj.get("gasPrice"), int(rpc.call(lambda w3: w3.eth.gas_price)))
    if not tx_to or not tx_data:
        raise RuntimeError("swap 返回缺少 tx.to 或 tx.data")

    tx_for_sign: Dict[str, Any] = {
        "chainId": chain_id,
        "from": from_addr,
        "to": Web3.to_checksum_address(tx_to),
        "value": tx_value,
        "data": tx_data,
        "nonce": nonce,
        "gas": tx_gas,
        "gasPrice": tx_gas_price,
    }
    signed = account.sign_transaction(tx_for_sign)
    signed_tx = signed.raw_transaction.hex()
    if not signed_tx.startswith("0x"):
        signed_tx = "0x" + signed_tx

    simulate = client.post(
        "/api/v6/dex/pre-transaction/simulate",
        {
            "chainIndex": str(args.chain_index),
            "fromAddress": from_addr,
            "toAddress": Web3.to_checksum_address(tx_to),
            "txAmount": str(tx_value),
            "extJson": {"inputData": tx_data},
        },
    )

    broadcast = client.post(
        "/api/v6/dex/pre-transaction/broadcast-transaction",
        {
            "signedTx": signed_tx,
            "chainIndex": str(args.chain_index),
            "address": from_addr,
        },
    )

    orders = None
    code = str((broadcast.get("response") or {}).get("code"))
    data = (broadcast.get("response") or {}).get("data") or []
    if code == "0" and data:
        order_id = data[0].get("orderId")
        if order_id:
            time.sleep(args.poll_seconds)
            orders = client.get(
                "/api/v6/dex/post-transaction/orders",
                {
                    "address": from_addr,
                    "chainIndex": str(args.chain_index),
                    "orderId": str(order_id),
                },
            )

    out = {
        "from": from_addr,
        "chain_id": chain_id,
        "quote": quote,
        "swap": swap,
        "derived_tx_for_signing": {
            "nonce": nonce,
            "to": tx_to,
            "value": str(tx_value),
            "gas": tx_gas,
            "gas_price": str(tx_gas_price),
            "data": tx_data,
            "tx_hash_local": signed.hash.hex(),
        },
        "simulate": simulate,
        "broadcast": broadcast,
        "orders": orders,
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
