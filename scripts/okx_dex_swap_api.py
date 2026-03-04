import argparse
import json
from typing import Dict, Tuple

from okx_api_client import OkxApiClient


ACTION_MAP: Dict[str, Tuple[str, str]] = {
    "supported-chain": ("GET", "/api/v6/dex/aggregator/supported/chain"),
    "get-liquidity": ("GET", "/api/v6/dex/aggregator/get-liquidity"),
    "approve-transaction": ("GET", "/api/v6/dex/aggregator/approve-transaction"),
    "quote": ("GET", "/api/v6/dex/aggregator/quote"),
    "swap-instruction": ("GET", "/api/v6/dex/aggregator/swap-instruction"),
    "swap": ("GET", "/api/v6/dex/aggregator/swap"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OKX DEX Swap 通用调用")
    parser.add_argument("--action", required=True, choices=sorted(ACTION_MAP.keys()), help="接口动作")
    parser.add_argument("--query-json", default="{}", help="GET 查询参数 JSON")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP 超时秒数")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _method, path = ACTION_MAP[args.action]
    query = json.loads(args.query_json)
    client = OkxApiClient(timeout=args.timeout)
    result = client.get(path, query)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
