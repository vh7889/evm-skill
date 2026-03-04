import argparse
import json
from typing import Dict, Tuple

from okx_api_client import OkxApiClient


ACTION_MAP: Dict[str, Tuple[str, str]] = {
    "supported-chain": ("GET", "/api/v6/dex/pre-transaction/supported/chain"),
    "gas-price": ("GET", "/api/v6/dex/pre-transaction/gas-price"),
    "gas-limit": ("POST", "/api/v6/dex/pre-transaction/gas-limit"),
    "simulate": ("POST", "/api/v6/dex/pre-transaction/simulate"),
    "broadcast": ("POST", "/api/v6/dex/pre-transaction/broadcast-transaction"),
    "orders": ("GET", "/api/v6/dex/post-transaction/orders"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OKX Onchain Gateway 通用调用")
    parser.add_argument("--action", required=True, choices=sorted(ACTION_MAP.keys()), help="接口动作")
    parser.add_argument("--query-json", default="{}", help="GET 查询参数 JSON")
    parser.add_argument("--body-json", default="{}", help="POST 请求体 JSON")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP 超时秒数")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    method, path = ACTION_MAP[args.action]
    query = json.loads(args.query_json)
    body = json.loads(args.body_json)
    client = OkxApiClient(timeout=args.timeout)

    if method == "GET":
        result = client.get(path, query)
    else:
        result = client.post(path, body)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
