import argparse
import base64
import hashlib
import hmac
import json
import os
import time
from decimal import Decimal
from typing import Dict, Tuple

import requests
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware


BASE_URL = "https://bopenapi.bgwapi.io"
DEFAULT_API_KEY = "4843D8C3F1E20772C0E634EDACC5C5F9A0E2DC92"
DEFAULT_API_SECRET = "F2ABFDC684BDC6775FD6286B8D06A3AAD30FD587"
DEFAULT_PARTNER_CODE = "bgw_swap_public"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="单钱包 Bitget 路由 Swap（EVM）")
    parser.add_argument("--private-key", required=True, help="钱包私钥")
    parser.add_argument("--rpc", required=True, help="RPC 地址")
    parser.add_argument("--chain", required=True, help="Bitget 链代码，例如 bnb/eth/base/arbitrum")
    parser.add_argument("--from-contract", required=True, help="from token 合约地址，原生币传空字符串")
    parser.add_argument("--to-contract", required=True, help="to token 合约地址，原生币传空字符串")
    parser.add_argument("--amount", required=True, help="swap 数量（人类可读）")
    parser.add_argument("--slippage", type=float, help="可选，自定义滑点，例如 0.5%%")
    parser.add_argument("--receipt-timeout", type=int, default=180, help="回执超时秒数")
    parser.add_argument(
        "--gas-price-gwei",
        type=float,
        help="可选，手动指定 gasPrice（gwei）；不填则自动读取链上实时 gasPrice",
    )
    args = parser.parse_args()
    if Decimal(args.amount) <= 0:
        raise ValueError("amount 必须 > 0")
    return args


def sign_request(path: str, body_str: str, api_key: str, api_secret: str, timestamp: str) -> str:
    content = {
        "apiPath": path,
        "body": body_str,
        "x-api-key": api_key,
        "x-api-timestamp": timestamp,
    }
    payload = json.dumps(dict(sorted(content.items())), separators=(",", ":"))
    sig = hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.b64encode(sig).decode()


def api_request(path: str, body: Dict) -> Dict:
    api_key = os.environ.get("BGW_API_KEY", DEFAULT_API_KEY)
    api_secret = os.environ.get("BGW_API_SECRET", DEFAULT_API_SECRET)
    timestamp = str(int(time.time() * 1000))
    body_str = json.dumps(body, separators=(",", ":"), sort_keys=True)
    signature = sign_request(path, body_str, api_key, api_secret, timestamp)
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "x-api-timestamp": timestamp,
        "x-api-signature": signature,
    }
    if "/swapx/" in path:
        headers["Partner-Code"] = os.environ.get("BGW_PARTNER_CODE", DEFAULT_PARTNER_CODE)
    resp = requests.post(BASE_URL + path, data=body_str, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def get_data_or_raise(result: Dict) -> Dict:
    if "data" in result and result["data"] is not None:
        return result["data"]
    if result.get("status") == 0 and isinstance(result.get("data"), dict):
        return result["data"]
    raise RuntimeError(json.dumps(result, ensure_ascii=False))


def parse_int(v) -> int:
    if v is None:
        return 0
    if isinstance(v, int):
        return v
    s = str(v).strip()
    if s.startswith("0x") or s.startswith("0X"):
        return int(s, 16)
    if "." in s:
        return int(Decimal(s))
    return int(s)


def normalize_amount_to_balance(
    web3: Web3, wallet_addr: str, from_contract: str, amount_text: str
) -> str:
    if from_contract.strip() == "":
        return amount_text

    token_addr = Web3.to_checksum_address(from_contract)
    abi = [
        {
            "name": "decimals",
            "type": "function",
            "stateMutability": "view",
            "inputs": [],
            "outputs": [{"name": "", "type": "uint8"}],
        },
        {
            "name": "balanceOf",
            "type": "function",
            "stateMutability": "view",
            "inputs": [{"name": "owner", "type": "address"}],
            "outputs": [{"name": "", "type": "uint256"}],
        },
    ]
    c = web3.eth.contract(address=token_addr, abi=abi)
    decimals = int(c.functions.decimals().call())
    balance_raw = int(c.functions.balanceOf(Web3.to_checksum_address(wallet_addr)).call())
    req_raw = int(Decimal(amount_text) * (Decimal(10) ** decimals))

    if req_raw > balance_raw:
        diff = req_raw - balance_raw
        if diff <= 10:
            req_raw = balance_raw
        else:
            raise RuntimeError(f"输入数量超过余额: req={req_raw}, balance={balance_raw}")

    normalized = (Decimal(req_raw) / (Decimal(10) ** decimals)).normalize()
    return format(normalized, "f")


def extract_evm_tx_fields(swap_data: Dict) -> Tuple[str, str, int, int]:
    to_addr = (
        swap_data.get("to")
        or swap_data.get("contract")
        or swap_data.get("txTo")
        or swap_data.get("router")
        or swap_data.get("contractAddress")
    )
    call_data = (
        swap_data.get("data")
        or swap_data.get("calldata")
        or swap_data.get("txData")
        or swap_data.get("callData")
    )
    tx_value = parse_int(swap_data.get("value") or swap_data.get("txValue") or 0)
    gas_limit = parse_int(
        swap_data.get("gas") or swap_data.get("gasLimit") or swap_data.get("computeUnits") or 0
    )
    if not to_addr or not call_data:
        raise RuntimeError(f"无法从 swap 数据解析 EVM 交易字段: {json.dumps(swap_data, ensure_ascii=False)}")
    return to_addr, call_data, tx_value, gas_limit


def main() -> None:
    args = parse_args()
    web3 = Web3(Web3.HTTPProvider(args.rpc))
    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    print(f"rpc_connected={web3.is_connected()}")
    if not web3.is_connected():
        raise RuntimeError("RPC 连接失败")

    account = web3.eth.account.from_key(args.private_key)
    wallet_addr = account.address
    chain_id = web3.eth.chain_id
    effective_amount = normalize_amount_to_balance(
        web3, wallet_addr, args.from_contract, args.amount
    )

    quote_body = {
        "fromChain": args.chain,
        "fromContract": args.from_contract,
        "toChain": args.chain,
        "toContract": args.to_contract,
        "fromAmount": str(effective_amount),
        "estimateGas": True,
        "fromAddress": wallet_addr,
    }
    quote_res = api_request("/bgw-pro/swapx/pro/quote", quote_body)
    quote_data = get_data_or_raise(quote_res)
    market = quote_data.get("market")
    if not market:
        raise RuntimeError(f"quote 缺少 market: {json.dumps(quote_res, ensure_ascii=False)}")

    swap_body = {
        "fromChain": args.chain,
        "fromContract": args.from_contract,
        "toChain": args.chain,
        "toContract": args.to_contract,
        "fromAmount": str(effective_amount),
        "fromAddress": wallet_addr,
        "toAddress": wallet_addr,
        "market": market,
    }
    if args.slippage is not None:
        swap_body["slippage"] = args.slippage
    swap_res = api_request("/bgw-pro/swapx/pro/swap", swap_body)
    swap_data = get_data_or_raise(swap_res)
    to_addr, call_data, tx_value, gas_limit = extract_evm_tx_fields(swap_data)
    if tx_value == 0 and args.from_contract.strip() == "":
        tx_value = int(web3.to_wei(Decimal(effective_amount), "ether"))

    nonce = web3.eth.get_transaction_count(wallet_addr, "pending")
    tx = {
        "chainId": chain_id,
        "from": wallet_addr,
        "to": Web3.to_checksum_address(to_addr),
        "value": tx_value,
        "data": call_data,
        "nonce": nonce,
    }
    if gas_limit > 0:
        tx["gas"] = int(gas_limit * 1.2)
    else:
        tx["gas"] = int(web3.eth.estimate_gas(tx) * 1.2)

    if args.gas_price_gwei is not None:
        tx["gasPrice"] = int(web3.to_wei(Decimal(str(args.gas_price_gwei)), "gwei"))
    else:
        tx["gasPrice"] = int(web3.eth.gas_price)

    signed = account.sign_transaction(tx)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction).hex()
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=args.receipt_timeout)

    print(f"wallet={wallet_addr}")
    print(f"chain_id={chain_id}")
    print(f"amount={effective_amount}")
    print(f"market={market}")
    print(f"gas_price_gwei={tx['gasPrice'] / 1e9}")
    print(f"tx_hash={tx_hash}")
    print(f"status={int(receipt.status)}")


if __name__ == "__main__":
    main()
