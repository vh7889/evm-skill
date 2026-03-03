import threading
import time
from typing import Callable, List, Sequence

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware


def add_rpc_resilience_args(parser) -> None:
    parser.add_argument(
        "--rpc-backup",
        action="append",
        default=[],
        help="可选，备用 RPC，可重复传入多次；主 RPC 失败时自动切换",
    )
    parser.add_argument(
        "--rpc-max-retries",
        type=int,
        default=4,
        help="单次 RPC 调用最大重试次数（默认 4）",
    )
    parser.add_argument(
        "--rpc-timeout",
        type=int,
        default=15,
        help="RPC 请求超时秒数（默认 15）",
    )
    parser.add_argument(
        "--rpc-backoff-base",
        type=float,
        default=0.4,
        help="指数退避基准秒数（默认 0.4）",
    )


class ResilientRPC:
    def __init__(
        self,
        primary_rpc: str,
        backup_rpcs: Sequence[str] | None = None,
        timeout: int = 15,
        max_retries: int = 4,
        backoff_base: float = 0.4,
    ):
        self._rpcs: List[str] = [primary_rpc] + [r for r in (backup_rpcs or []) if r]
        if not self._rpcs:
            raise ValueError("至少需要一个 RPC")
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._idx = 0
        self._lock = threading.RLock()
        self._w3 = self._build_web3(self._rpcs[self._idx])

    @property
    def current_rpc(self) -> str:
        with self._lock:
            return self._rpcs[self._idx]

    def _build_web3(self, rpc: str) -> Web3:
        w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": self.timeout}))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        return w3

    def _switch_rpc(self) -> None:
        with self._lock:
            self._idx = (self._idx + 1) % len(self._rpcs)
            self._w3 = self._build_web3(self._rpcs[self._idx])

    def _is_retryable(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        keywords = [
            "429",
            "too many requests",
            "timeout",
            "timed out",
            "connection",
            "not connected",
            "temporarily unavailable",
            "gateway",
            "internal error",
            "rate limit",
            "missing trie node",
        ]
        return any(k in msg for k in keywords)

    def ensure_connected(self) -> bool:
        def _op(w3: Web3):
            cid = w3.eth.chain_id
            if cid is None:
                raise RuntimeError("rpc not connected")
            return True

        return bool(self.call(_op))

    def call(self, fn: Callable[[Web3], object]):
        last_exc = None
        for attempt in range(self.max_retries):
            try:
                with self._lock:
                    w3 = self._w3
                return fn(w3)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if not self._is_retryable(exc) or attempt == self.max_retries - 1:
                    raise
                self._switch_rpc()
                sleep_s = self.backoff_base * (2**attempt)
                time.sleep(min(sleep_s, 4.0))
        raise last_exc
