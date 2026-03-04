import json
import re
from decimal import Decimal
from typing import Any, Dict, List, Sequence

from web3 import Web3


def parse_abi_input(raw: str) -> List[Any]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("ABI 为空")

    if text.startswith("["):
        try:
            abi = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"ABI JSON 解析失败: {e}") from e
        if not isinstance(abi, list):
            raise ValueError("ABI 必须是 JSON 数组")
        return abi

    abi = parse_human_readable_abi(text)
    if not abi:
        raise ValueError("无法从文本中解析 ABI，请检查 function 声明格式")
    return abi


def _split_by_comma_top_level(s: str) -> List[str]:
    out: List[str] = []
    buf: List[str] = []
    depth = 0
    for ch in s:
        if ch == "," and depth == 0:
            out.append("".join(buf).strip())
            buf = []
            continue
        if ch in ("(", "["):
            depth += 1
        elif ch in (")", "]"):
            depth -= 1
        buf.append(ch)
    out.append("".join(buf).strip())
    return [x for x in out if x]


def _normalize_solidity_type(raw_type: str) -> str:
    t = raw_type.strip()
    if not t:
        raise ValueError("空参数类型")

    t = re.sub(r"\b(memory|calldata|storage|indexed)\b", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = t.replace("address payable", "address")

    # uint/int 简写统一为 256 位，便于 ABI 一致性
    t = re.sub(r"\buint\b", "uint256", t)
    t = re.sub(r"\bint\b", "int256", t)

    return t


def _parse_param_decl(param_text: str) -> Dict[str, Any]:
    tokens = param_text.strip().split()
    if not tokens:
        raise ValueError("空参数声明")

    # 参数形式支持：
    # 1) "address"
    # 2) "address to"
    # 3) "address payable to"
    # 4) "uint[] memory amounts"
    if len(tokens) == 1:
        param_type = _normalize_solidity_type(tokens[0])
        name = ""
    else:
        name = tokens[-1]
        type_tokens = tokens[:-1]
        param_type = _normalize_solidity_type(" ".join(type_tokens))
        if name in {"memory", "calldata", "storage", "indexed", "payable"}:
            # 没有参数名的情况，如 "address payable"
            param_type = _normalize_solidity_type(param_text)
            name = ""

    return {
        "internalType": param_type,
        "name": name if re.fullmatch(r"[A-Za-z_]\w*", name) else "",
        "type": param_type,
    }


def parse_human_readable_abi(text: str) -> List[Dict[str, Any]]:
    abi: List[Dict[str, Any]] = []
    lines = [x.strip() for x in re.split(r"[;\n]+", text) if x.strip()]

    for line in lines:
        line = re.sub(r"\s+", " ", line).strip()

        # 支持: function transfer(address,uint256) public returns (bool)
        # 支持: transfer(address,uint256)
        m = re.match(r"^(?:function\s+)?([A-Za-z_]\w*)\s*\((.*?)\)\s*(.*)$", line)
        if not m:
            continue

        fn_name = m.group(1)
        inputs_text = m.group(2).strip()
        tail = m.group(3).strip()

        inputs: List[Dict[str, Any]] = []
        if inputs_text:
            for p in _split_by_comma_top_level(inputs_text):
                inputs.append(_parse_param_decl(p))

        outputs: List[Dict[str, Any]] = []
        ret_match = re.search(r"\breturns\s*\((.*)\)", tail)
        if ret_match:
            returns_text = ret_match.group(1).strip()
            if returns_text:
                for p in _split_by_comma_top_level(returns_text):
                    outputs.append(_parse_param_decl(p))

        if re.search(r"\bpayable\b", tail):
            state_mutability = "payable"
        elif re.search(r"\bview\b", tail):
            state_mutability = "view"
        elif re.search(r"\bpure\b", tail):
            state_mutability = "pure"
        else:
            state_mutability = "nonpayable"

        abi.append(
            {
                "type": "function",
                "name": fn_name,
                "inputs": inputs,
                "outputs": outputs,
                "stateMutability": state_mutability,
            }
        )

    return abi


def parse_args_json(args_json: str) -> List[Any]:
    try:
        args = json.loads(args_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"args-json 解析失败: {e}") from e
    if not isinstance(args, list):
        raise ValueError("args-json 必须是 JSON 数组")
    return args


def _canonical_type(param: Dict[str, Any]) -> str:
    t = str(param.get("type", ""))
    if not t:
        raise ValueError("ABI 参数缺少 type")
    if not t.startswith("tuple"):
        return t

    components = param.get("components") or []
    if not isinstance(components, list):
        raise ValueError("tuple 参数的 components 非法")

    inner = ",".join(_canonical_type(c) for c in components)
    suffix = t[len("tuple") :]
    return f"({inner}){suffix}"


def _type_matches_signature(param: Dict[str, Any], sig_type: str) -> bool:
    return _canonical_type(param) == sig_type.strip()


def _extract_signature_types(fn_signature: str) -> tuple[str, List[str]]:
    m = re.fullmatch(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*", fn_signature)
    if not m:
        raise ValueError("function-signature 格式非法，示例: transfer(address,uint256)")
    fn_name = m.group(1)
    raw = m.group(2).strip()
    if raw == "":
        return fn_name, []

    out: List[str] = []
    buf = []
    depth = 0
    for ch in raw:
        if ch == "," and depth == 0:
            out.append("".join(buf).strip())
            buf = []
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        buf.append(ch)
    out.append("".join(buf).strip())
    return fn_name, out


def select_function_abi(
    abi: Sequence[Any],
    function_name: str,
    function_signature: str | None,
    arg_count: int,
) -> Dict[str, Any]:
    fns = [x for x in abi if isinstance(x, dict) and x.get("type") == "function"]

    if function_signature:
        sig_name, sig_types = _extract_signature_types(function_signature)
        if sig_name != function_name:
            raise ValueError("function 与 function-signature 的函数名不一致")

        for fn in fns:
            if fn.get("name") != function_name:
                continue
            inputs = fn.get("inputs") or []
            if len(inputs) != len(sig_types):
                continue
            if all(_type_matches_signature(inputs[i], sig_types[i]) for i in range(len(sig_types))):
                return fn
        raise ValueError(f"ABI 中找不到函数签名: {function_signature}")

    named = [fn for fn in fns if fn.get("name") == function_name]
    if not named:
        raise ValueError(f"ABI 中找不到函数: {function_name}")

    by_count = [fn for fn in named if len(fn.get("inputs") or []) == arg_count]
    if len(by_count) == 1:
        return by_count[0]
    if len(by_count) > 1:
        raise ValueError(
            f"函数 {function_name} 存在重载，请使用 --function-signature 指定，例如 {function_name}(...)"
        )

    expected = sorted({len(fn.get("inputs") or []) for fn in named})
    raise ValueError(f"函数 {function_name} 参数个数不匹配，当前传入 {arg_count}，ABI 可选 {expected}")


def _parse_int_like(value: Any, abi_type: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{abi_type} 参数不接受布尔值")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"{abi_type} 参数不能是小数")
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            raise ValueError(f"{abi_type} 参数为空字符串")
        if s.startswith(("0x", "0X")):
            return int(s, 16)
        if re.fullmatch(r"[-+]?\d+", s):
            return int(s)
        if re.fullmatch(r"[-+]?\d+\.\d+", s):
            d = Decimal(s)
            if d != d.to_integral_value():
                raise ValueError(f"{abi_type} 参数不能是小数")
            return int(d)
    raise ValueError(f"{abi_type} 参数无法转为整数: {value}")


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value in (0, 0.0):
            return False
        if value in (1, 1.0):
            return True
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("true", "1", "yes", "y"):
            return True
        if s in ("false", "0", "no", "n"):
            return False
    raise ValueError(f"bool 参数非法: {value}")


def _normalize_bytes(value: Any, abi_type: str) -> Any:
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
    elif isinstance(value, str) and value.startswith("0x"):
        body = value[2:]
        if len(body) % 2 != 0:
            raise ValueError(f"{abi_type} 参数 16 进制长度必须是偶数")
        int(body or "0", 16)
        raw = bytes.fromhex(body)
    else:
        raise ValueError(f"{abi_type} 参数需要 bytes 或 0x 十六进制字符串")

    m = re.fullmatch(r"bytes(\d+)", abi_type)
    if m:
        size = int(m.group(1))
        if len(raw) != size:
            raise ValueError(f"{abi_type} 长度必须是 {size} 字节，当前 {len(raw)}")
    return "0x" + raw.hex()


def _normalize_tuple(value: Any, components: Sequence[Dict[str, Any]]) -> tuple[Any, ...]:
    if isinstance(value, dict):
        out = []
        for comp in components:
            name = comp.get("name")
            if not name:
                raise ValueError("tuple 参数使用对象传参时，ABI 子字段必须有 name")
            if name not in value:
                raise ValueError(f"tuple 参数缺少字段: {name}")
            out.append(_normalize_value(value[name], comp))
        return tuple(out)

    if not isinstance(value, (list, tuple)):
        raise ValueError("tuple 参数需要数组或对象")
    if len(value) != len(components):
        raise ValueError(f"tuple 参数长度不匹配，期望 {len(components)}，实际 {len(value)}")

    return tuple(_normalize_value(value[i], components[i]) for i in range(len(components)))


def _normalize_array(value: Any, inner_type: str, fixed_len: str, param: Dict[str, Any]) -> List[Any]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{param.get('type')} 参数需要数组")
    if fixed_len != "" and len(value) != int(fixed_len):
        raise ValueError(f"{param.get('type')} 固定长度应为 {fixed_len}，实际 {len(value)}")

    child = dict(param)
    child["type"] = inner_type
    return [_normalize_value(v, child) for v in value]


def _normalize_value(value: Any, param: Dict[str, Any]) -> Any:
    abi_type = str(param.get("type", ""))
    arr = re.fullmatch(r"(.+)\[(\d*)\]", abi_type)
    if arr:
        inner_type, fixed_len = arr.group(1), arr.group(2)
        return _normalize_array(value, inner_type, fixed_len, param)

    if abi_type == "address":
        if not isinstance(value, str) or not Web3.is_address(value):
            raise ValueError(f"address 参数非法: {value}")
        return Web3.to_checksum_address(value)

    if abi_type.startswith("uint"):
        v = _parse_int_like(value, abi_type)
        if v < 0:
            raise ValueError(f"{abi_type} 不能为负数")
        return v

    if abi_type.startswith("int"):
        return _parse_int_like(value, abi_type)

    if abi_type == "bool":
        return _normalize_bool(value)

    if abi_type == "string":
        return value if isinstance(value, str) else str(value)

    if abi_type.startswith("bytes"):
        return _normalize_bytes(value, abi_type)

    if abi_type.startswith("tuple"):
        components = param.get("components") or []
        if not isinstance(components, list):
            raise ValueError("tuple 参数 components 非法")
        return _normalize_tuple(value, components)

    return value


def normalize_function_args(raw_args: Sequence[Any], function_abi: Dict[str, Any]) -> List[Any]:
    inputs = function_abi.get("inputs") or []
    if len(inputs) != len(raw_args):
        raise ValueError(f"参数个数不匹配，期望 {len(inputs)}，实际 {len(raw_args)}")
    return [_normalize_value(raw_args[i], inputs[i]) for i in range(len(inputs))]
