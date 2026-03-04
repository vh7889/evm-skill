import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, List

from web3 import Web3

from contract_arg_utils import (
    normalize_function_args,
    parse_abi_input,
    parse_args_json,
    select_function_abi,
)
from rpc_resilient import ResilientRPC, add_rpc_resilience_args


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="单钱包 write_contract 调用（ABI + function + args）")
    parser.add_argument("--private-key", required=True, help="调用钱包私钥")
    parser.add_argument("--contract", required=True, help="目标合约地址")
    parser.add_argument("--rpc", required=True, help="RPC 地址")
    parser.add_argument("--function", required=True, help="函数名，例如 transfer")
    parser.add_argument(
        "--function-signature",
        help="可选，函数签名（用于重载函数），例如 transfer(address,uint256)",
    )
    parser.add_argument(
        "--abi-json",
        help="ABI 内容字符串（支持 JSON ABI 或 function 声明文本，与 --abi-file 二选一）",
    )
    parser.add_argument(
        "--abi-file",
        help="ABI 文件路径（支持 JSON ABI 或 function 声明文本，与 --abi-json 二选一）",
    )
    parser.add_argument(
        "--args-json",
        default="[]",
        help="函数参数 JSON 数组，例如 '[\"0xabc...\",\"1000000000000000000\"]'",
    )
    parser.add_argument("--value", default="0", help="可选，附带原生币数量（人类可读），默认 0")
    parser.add_argument("--receipt-timeout", type=int, default=180, help="回执超时秒数")
    parser.add_argument(
        "--gas-price-gwei",
        type=float,
        help="可选，手动指定 gasPrice（gwei）；不填则自动读取链上实时 gasPrice",
    )
    add_rpc_resilience_args(parser)
    args = parser.parse_args()

    if not Web3.is_address(args.contract):
        raise ValueError("contract 地址非法")
    if Decimal(args.value) < 0:
        raise ValueError("value 必须 >= 0")
    if bool(args.abi_json) == bool(args.abi_file):
        raise ValueError("--abi-json 与 --abi-file 必须二选一")
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
    print(f"rpc_connected={rpc.ensure_connected()}")
    print(f"rpc_current={rpc.current_rpc}")
    if not rpc.ensure_connected():
        raise RuntimeError("RPC 连接失败")

    account = rpc.call(lambda w3: w3.eth.account.from_key(args.private_key))
    from_addr = account.address
    contract_addr = Web3.to_checksum_address(args.contract)
    chain_id = int(rpc.call(lambda w3: w3.eth.chain_id))
    nonce = int(rpc.call(lambda w3: w3.eth.get_transaction_count(from_addr, "pending")))
    value_wei = int(rpc.call(lambda w3: w3.to_wei(Decimal(args.value), "ether")))

    def estimate_tx() -> int:
        def _op(w3: Web3) -> int:
            contract = w3.eth.contract(address=contract_addr, abi=abi)
            fn_call = build_contract_function(contract, args.function, args.function_signature, fn_args)
            est = fn_call.estimate_gas({"from": from_addr, "value": value_wei})
            return int(est)

        return int(rpc.call(_op))

    gas_limit = int(estimate_tx() * 1.2)
    if args.gas_price_gwei is not None:
        gas_price = int(rpc.call(lambda w3: w3.to_wei(Decimal(str(args.gas_price_gwei)), "gwei")))
    else:
        gas_price = int(rpc.call(lambda w3: w3.eth.gas_price))

    def build_tx_data() -> str:
        def _op(w3: Web3) -> str:
            contract = w3.eth.contract(address=contract_addr, abi=abi)
            fn_call = build_contract_function(contract, args.function, args.function_signature, fn_args)
            tx = fn_call.build_transaction(
                {
                    "chainId": chain_id,
                    "from": from_addr,
                    "nonce": nonce,
                    "value": value_wei,
                    "gas": gas_limit,
                    "gasPrice": gas_price,
                }
            )
            return tx["data"]

        return str(rpc.call(_op))

    tx_data = build_tx_data()
    tx = {
        "chainId": chain_id,
        "from": from_addr,
        "to": contract_addr,
        "value": value_wei,
        "data": tx_data,
        "nonce": nonce,
        "gas": gas_limit,
        "gasPrice": gas_price,
    }

    signed = account.sign_transaction(tx)
    tx_hash = rpc.call(lambda w3: w3.eth.send_raw_transaction(signed.raw_transaction).hex())
    receipt = rpc.call(lambda w3: w3.eth.wait_for_transaction_receipt(tx_hash, timeout=args.receipt_timeout))

    print(f"from={from_addr}")
    print(f"contract={contract_addr}")
    print(f"function={args.function}")
    print(f"args={json.dumps(fn_args, ensure_ascii=False, default=str)}")
    print(f"value={args.value}")
    print(f"gas_limit={gas_limit}")
    print(f"gas_price_gwei={gas_price / 1e9}")
    print(f"tx_hash={tx_hash}")
    print(f"status={int(receipt.status)}")


if __name__ == "__main__":
    main()
