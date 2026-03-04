import argparse
import json
import re
import sys
from typing import Any, Dict, List, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from eth_abi import decode, encode

BASE = "https://www.4byte.directory/api/v1/signatures/"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="根据函数选择器查询 4byte 候选函数签名")
    p.add_argument("--selector", required=True, help="4-byte 选择器，如 0xc2998238")
    p.add_argument("--calldata", help="可选，完整 calldata（0x + selector + 参数）")
    p.add_argument("--raw", action="store_true", help="输出 4byte 原始 JSON")
    p.add_argument("--json", action="store_true", help="输出结构化 JSON 结果")
    return p.parse_args()


def normalize_selector(s: str) -> str:
    s = s.strip().lower()
    if not s.startswith("0x"):
        s = "0x" + s
    if len(s) != 10:
        raise ValueError("selector 必须是 4-byte（0x + 8 hex）")
    int(s[2:], 16)
    return s


def normalize_calldata(s: str) -> str:
    s = s.strip().lower()
    if not s.startswith("0x"):
        raise ValueError("calldata 必须是 0x 开头")
    body = s[2:]
    if len(body) < 8 or len(body) % 2 != 0:
        raise ValueError("calldata 长度非法")
    int(body, 16)
    return s


def fetch_4byte(selector: str) -> Dict[str, Any]:
    url = BASE + "?" + urlencode({"format": "json", "hex_signature": selector})
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/145.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def split_top_level(arg_text: str) -> List[str]:
    out: List[str] = []
    cur: List[str] = []
    depth = 0
    for ch in arg_text:
        if ch == "," and depth == 0:
            item = "".join(cur).strip()
            if item:
                out.append(item)
            cur = []
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        out.append(tail)
    return out


def parse_signature_types(text_signature: str) -> List[str]:
    m = re.match(r"^[^(]+\((.*)\)$", text_signature)
    if not m:
        return []
    inside = m.group(1).strip()
    if inside == "":
        return []
    return split_top_level(inside)


def to_jsonable(v: Any) -> Any:
    if isinstance(v, bytes):
        return "0x" + v.hex()
    if isinstance(v, (list, tuple)):
        return [to_jsonable(x) for x in v]
    return v


def _iter_values(type_name: str, value: Any) -> List[Any]:
    if type_name.endswith("[]") and isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def semantic_adjust(signature: str, types: List[str], decoded: Tuple[Any, ...]) -> int:
    adjust = 0
    fn_name = signature.split("(", 1)[0]
    if fn_name.startswith("_") or "watch_tg" in fn_name or "bytecode" in fn_name:
        adjust -= 5

    for t, v in zip(types, decoded):
        vals = _iter_values(t, v)
        if t == "address" or t == "address[]":
            for one in vals:
                if isinstance(one, str) and one.startswith("0x"):
                    n = int(one, 16)
                    # 过短地址（高位几乎全 0）通常是“把数值误解成地址”的假阳性
                    if n < (1 << 80):
                        adjust -= 25
    return adjust


def evaluate_candidate(signature: str, calldata: str) -> Dict[str, Any]:
    types = parse_signature_types(signature)
    payload_hex = calldata[10:]
    payload = bytes.fromhex(payload_hex)

    result: Dict[str, Any] = {
        "signature": signature,
        "types": types,
        "compatible": False,
        "score": 0,
        "reason": "",
    }

    try:
        decoded = decode(types, payload)
        result["decoded"] = to_jsonable(decoded)
        result["score"] += 60
    except Exception as e:
        result["reason"] = f"decode_failed: {e}"
        return result

    try:
        reencoded = encode(types, decoded).hex()
        match = reencoded == payload_hex
        result["reencode_match"] = match
        if match:
            result["score"] += 30
        else:
            result["score"] += 10
    except Exception as e:
        result["reencode_match"] = False
        result["reason"] = f"reencode_failed: {e}"
        return result

    if all("[" not in t and t != "bytes" and t != "string" for t in types):
        expected = 64 * len(types)
        if len(payload_hex) == expected:
            result["score"] += 10

    result["score"] += semantic_adjust(signature, types, decoded)

    result["compatible"] = True
    result["reason"] = "ok"
    return result


def choose_best(cands: List[Dict[str, Any]]) -> Tuple[Dict[str, Any] | None, float]:
    ok = [c for c in cands if c.get("compatible")]
    if not ok:
        return None, 0.0
    ok.sort(key=lambda x: x.get("score", 0), reverse=True)
    top = ok[0]
    second = ok[1] if len(ok) > 1 else None
    top_score = float(top.get("score", 0))
    gap = top_score - float(second.get("score", 0)) if second else top_score
    confidence = min(0.99, max(0.35, top_score / 100.0 + min(0.25, gap / 100.0)))
    return top, round(confidence, 2)


def main() -> None:
    args = parse_args()
    selector = normalize_selector(args.selector)
    calldata = normalize_calldata(args.calldata) if args.calldata else None
    if calldata and calldata[:10] != selector:
        raise ValueError("selector 与 calldata 的前 4-byte 不一致")

    data = fetch_4byte(selector)
    if args.raw:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    raw_results = data.get("results", [])
    evaluated: List[Dict[str, Any]] = []
    for item in raw_results:
        sig = item.get("text_signature", "")
        row = {
            "id": item.get("id"),
            "created_at": item.get("created_at"),
            "signature": sig,
        }
        if calldata:
            row.update(evaluate_candidate(sig, calldata))
        evaluated.append(row)

    best = None
    confidence = 0.0
    if calldata:
        best, confidence = choose_best(evaluated)

    out = {
        "selector": selector,
        "count": data.get("count", 0),
        "calldata_provided": bool(calldata),
        "best_guess": best.get("signature") if best else None,
        "confidence": confidence if calldata else None,
        "results": evaluated,
    }

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    print(f"selector={selector}")
    print(f"count={out['count']}")
    if calldata:
        print(f"best_guess={out['best_guess']}")
        print(f"confidence={out['confidence']}")
    for i, row in enumerate(evaluated, start=1):
        if calldata:
            print(
                f"{i}. {row.get('signature')} | compatible={row.get('compatible')} "
                f"score={row.get('score')} reason={row.get('reason')}"
            )
            if row.get("compatible"):
                print(f"   decoded={row.get('decoded')}")
        else:
            print(f"{i}. {row.get('signature')}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"error={e}", file=sys.stderr)
        raise
