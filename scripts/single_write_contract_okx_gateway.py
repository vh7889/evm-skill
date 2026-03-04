import argparse
import json
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

from web3 import Web3

from contract_arg_utils import (
    normalize_function_args,
    parse_abi_input,
    parse_args_json,
    select_function_abi,
)
from okx_api_client import OkxApiClient
from rpc_resilient import ResilientRPC, add_rpc_resilience_args


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="单钱包 write_contract（OKX Gateway: simulate -> broadcast）")
    parser.add_argument("--private-key", required=True, help="调用钱包私钥")
    parser.add_argument("--contract", required=True, help="目标合约地址")
    parser.add_argument("--rpc", required=True, help="RPC 地址")
    parser.add_argument("--chain-index", default="56", help="OKX chainIndex，默认 56(BSC)")
    parser.add_argument("--function", required=True, help="函数名，例如 transfer")
    parser.add_argument("--function-signature", help="可选，函数签名（用于重载），例如 transfer(address,uint256)")
    parser.add_argument("--abi-json", help="ABI 内容字符串（支持 JSON ABI 或 function 声明文本，与 --abi-file 二选一）")
    parser.add_argument("--abi-file", help="ABI 文件路径（支持 JSON ABI 或 function 声明文本，与 --abi-json 二选一）")
    parser.add_argument("--args-json", default="[]", help="函数参数 JSON 数组")
    parser.add_argument("--value", default="0", help="附带原生币数量（人类可读），默认 0")
    parser.add_argument("--gas-multiplier", type=float, default=1.2, help="gas 估算放大倍数，默认 1.2")
    parser.add_argument(
        "--gas-price-gwei",
        type=float,
        help="可选，手动指定 gasPrice（gwei）；不填则自动读取链上实时 gasPrice",
    )
    parser.add_argument("--poll-seconds", type=int, default=2, help="查询订单状态前等待秒数")
    add_rpc_resilience_args(parser)
    args = parser.parse_args()

    if not Web3.is_address(args.contract):
        raise ValueError("contract 地址非法")
    if Decimal(args.value) < 0:
        raise ValueError("value 必须 >= 0")
    if bool(args.abi_json) == bool(args.abi_file):
        raise ValueError("--abi-json 与 --abi-file 必须二选一")
    if args.gas_multiplier < 1:
        raise ValueError("gas-multiplier 必须 >= 1")
    return args


def load_abi(abi_json: str | None, abi_file: str | None) -> List[Any]:
    raw = abi_json
    if abi_file:
        raw = Path(abi_file).read_text(encoding="utf-8")
    return parse_abi_input(raw or "")


def build_contract_function(contract, fn_name: str, fn_signature: str | None, fn_args: List[Any]):
    if fn_signature:
        fn = contract.get_function_by_signature(fn_signature)
    else:
        fn = contract.get_function_by_name(fn_name)
    return fn(*fn_args)


def main() -> None:
    args = parse_args()
    abi = load_abi(args.abi_json, args.abi_file)
    raw_fn_args = parse_args_json(args.args_json)
    fn_abi = select_function_abi(abi, args.function, args.function_signature, len(raw_fn_args))
    fn_args = normalize_function_args(raw_fn_args, fn_abi)

    rpc = ResilientRPC(
        primary_rpc=args.rpc,
        backup_rpcs=args.rpc_backup,
        timeout=args.rpc_timeout,
        max_retries=args.rpc_max_retries,
        backoff_base=args.rpc_backoff_base,
    )
    if not rpc.ensure_connected():
        raise RuntimeError("RPC 连接失败")

    client = OkxApiClient()

    account = rpc.call(lambda w3: w3.eth.account.from_key(args.private_key))
    from_addr = account.address
    contract_addr = Web3.to_checksum_address(args.contract)
    chain_id = int(rpc.call(lambda w3: w3.eth.chain_id))
    nonce = int(rpc.call(lambda w3: w3.eth.get_transaction_count(from_addr, "pending")))
    value_wei = int(rpc.call(lambda w3: w3.to_wei(Decimal(args.value), "ether")))

    def build_data_and_estimate() -> Dict[str, Any]:
        def _op(w3: Web3) -> Dict[str, Any]:
            contract = w3.eth.contract(address=contract_addr, abi=abi)
            fn_call = build_contract_function(contract, args.function, args.function_signature, fn_args)
            tx_for_build = fn_call.build_transaction(
                {
                    "chainId": chain_id,
                    "from": from_addr,
                    "nonce": nonce,
                    "value": value_wei,
                }
            )
            est = fn_call.estimate_gas({"from": from_addr, "value": value_wei})
            return {"data": str(tx_for_build["data"]), "estimate": int(est)}

        return rpc.call(_op)

    tx_tmp = build_data_and_estimate()
    tx_data = tx_tmp["data"]
    gas_limit = max(21_000, int(tx_tmp["estimate"] * args.gas_multiplier))
    if args.gas_price_gwei is not None:
        gas_price = int(rpc.call(lambda w3: w3.to_wei(Decimal(str(args.gas_price_gwei)), "gwei")))
    else:
        gas_price = int(rpc.call(lambda w3: w3.eth.gas_price))

    tx_for_sign = {
        "chainId": chain_id,
        "from": from_addr,
        "to": contract_addr,
        "value": value_wei,
        "data": tx_data,
        "nonce": nonce,
        "gas": gas_limit,
        "gasPrice": gas_price,
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
            "toAddress": contract_addr,
            "txAmount": str(value_wei),
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

    result = {
        "from": from_addr,
        "chain_id": chain_id,
        "contract": contract_addr,
        "function": args.function,
        "args": fn_args,
        "tx_meta": {
            "nonce": nonce,
            "value_wei": str(value_wei),
            "gas_limit": gas_limit,
            "gas_price_wei": str(gas_price),
            "data": tx_data,
            "tx_hash_local": signed.hash.hex(),
        },
        "simulate": simulate,
        "broadcast": broadcast,
        "orders": orders,
    }
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
