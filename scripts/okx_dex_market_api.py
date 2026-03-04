import argparse
import json
from typing import Dict, Tuple

from okx_api_client import OkxApiClient


ACTION_MAP: Dict[str, Tuple[str, str]] = {
    "supported-chain": ("GET", "/api/v6/dex/market/supported/chain"),
    "price": ("POST", "/api/v6/dex/market/price"),
    "trades": ("GET", "/api/v6/dex/market/trades"),
    "candles": ("GET", "/api/v6/dex/market/candles"),
    "historical-candles": ("GET", "/api/v6/dex/market/historical-candles"),
    "index-current-price": ("POST", "/api/v6/dex/index/current-price"),
    "index-historical-price": ("GET", "/api/v6/dex/index/historical-price"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OKX DEX Market 通用调用")
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
