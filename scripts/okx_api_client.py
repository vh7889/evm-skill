import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests


OKX_BASE_URL = "https://web3.okx.com"


def _iso_ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class OkxApiClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        passphrase: Optional[str] = None,
        base_url: str = OKX_BASE_URL,
        timeout: int = 30,
    ):
        self.api_key = api_key or os.getenv("OKX_API_KEY", "")
        self.secret_key = secret_key or os.getenv("OKX_SECRET_KEY", "")
        self.passphrase = passphrase or os.getenv("OKX_PASSPHRASE", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        if not self.api_key or not self.secret_key or not self.passphrase:
            raise ValueError("缺少 OKX 凭证，请设置 OKX_API_KEY / OKX_SECRET_KEY / OKX_PASSPHRASE")

        self.session = requests.Session()
        self.default_headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Origin": "https://web3.okx.com",
            "Referer": "https://web3.okx.com/",
        }

    def _sign_headers(self, method: str, request_path: str, body_str: str = "") -> Dict[str, str]:
        ts = _iso_ts()
        prehash = ts + method + request_path + body_str
        sign = base64.b64encode(
            hmac.new(self.secret_key.encode("utf-8"), prehash.encode("utf-8"), hashlib.sha256).digest()
        ).decode("utf-8")
        return {
            **self.default_headers,
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "OK-ACCESS-TIMESTAMP": ts,
        }

    def get(self, path: str, query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        query = query or {}
        query_str = urlencode({k: str(v) for k, v in query.items() if v is not None})
        request_path = f"{path}?{query_str}" if query_str else path
        headers = self._sign_headers("GET", request_path, "")
        resp = self.session.get(self.base_url + request_path, headers=headers, timeout=self.timeout)
        return {
            "request": {"method": "GET", "path": path, "query": query},
            "http_status": resp.status_code,
            "response": self._parse_json(resp),
        }

    def post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        body_str = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        headers = self._sign_headers("POST", path, body_str)
        resp = self.session.post(self.base_url + path, headers=headers, data=body_str, timeout=self.timeout)
        return {
            "request": {"method": "POST", "path": path, "body": body},
            "http_status": resp.status_code,
            "response": self._parse_json(resp),
        }

    @staticmethod
    def _parse_json(resp: requests.Response) -> Dict[str, Any]:
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return {"code": str(resp.status_code), "msg": resp.text}
