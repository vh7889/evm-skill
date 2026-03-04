import argparse
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Tuple

from eth_utils import to_checksum_address

from rpc_resilient import ResilientRPC, add_rpc_resilience_args


SUPPORTED_PREFIXES = (
    "uint",
    "int",
    "bytes",
)


@dataclass
class ParamItem:
    index: int
    type_name: str
    before: Any
    after: Any


def now_ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_hex_data(data: str) -> str:
    if not data.startswith("0x"):
        raise ValueError("data 必须是 0x 开头")
    body = data[2:]
    if len(body) < 8 or len(body) % 2 != 0:
        raise ValueError("data 长度非法")
    return data


def split_words(data: str) -> Tuple[str, List[str]]:
    hex_body = data[2:]
    selector = hex_body[:8]
    params_hex = hex_body[8:]
    if len(params_hex) % 64 != 0:
        raise ValueError("data 参数区长度不是 32-byte 对齐，疑似含动态参数，模式C不支持")
    words = [params_hex[i : i + 64] for i in range(0, len(params_hex), 64)]
    return selector, words


def parse_types(types_text: str) -> List[str]:
    items = [x.strip() for x in types_text.split(",") if x.strip()]
    if not items:
        raise ValueError("types 不能为空")
    return items


def is_supported_type(type_name: str) -> bool:
    if type_name == "address" or type_name == "bool" or type_name == "bytes32":
        return True
    if any(type_name.startswith(p) for p in SUPPORTED_PREFIXES):
        if type_name.startswith("bytes") and type_name != "bytes32":
            n = int(type_name[5:]) if type_name[5:].isdigit() else -1
            return 1 <= n <= 31
        if type_name.startswith("uint"):
            bits = type_name[4:]
            return bits.isdigit() and int(bits) % 8 == 0 and 8 <= int(bits) <= 256
        if type_name.startswith("int"):
            bits = type_name[3:]
            return bits.isdigit() and int(bits) % 8 == 0 and 8 <= int(bits) <= 256
    return type_name in ("uint", "int")


def decode_word(type_name: str, word_hex: str) -> Any:
    raw = bytes.fromhex(word_hex)
    if type_name == "address":
        return to_checksum_address("0x" + word_hex[-40:])
    if type_name == "bool":
        return int.from_bytes(raw, "big") != 0
    if type_name in ("uint",) or type_name.startswith("uint"):
        return int.from_bytes(raw, "big")
    if type_name in ("int",) or type_name.startswith("int"):
        u = int.from_bytes(raw, "big")
        if u >= (1 << 255):
            return u - (1 << 256)
        return u
    if type_name == "bytes32":
        return "0x" + word_hex
    if type_name.startswith("bytes"):
        n = int(type_name[5:])
        return "0x" + word_hex[: 2 * n]
    raise ValueError(f"不支持的类型: {type_name}")


def encode_word(type_name: str, value: Any) -> str:
    if type_name == "address":
        addr = to_checksum_address(str(value))
        return ("0" * 24) + addr[2:].lower()
    if type_name == "bool":
        v = str(value).lower() in ("1", "true", "yes") if isinstance(value, str) else bool(value)
        return ("0" * 63) + ("1" if v else "0")
    if type_name in ("uint",) or type_name.startswith("uint"):
        v = int(str(value), 10) if isinstance(value, str) else int(value)
        if v < 0:
            raise ValueError("uint 不能为负数")
        return format(v, "064x")
    if type_name in ("int",) or type_name.startswith("int"):
        v = int(str(value), 10) if isinstance(value, str) else int(value)
        if v < 0:
            v = (1 << 256) + v
        return format(v, "064x")
    if type_name == "bytes32":
        h = str(value)
        if not h.startswith("0x") or len(h) != 66:
            raise ValueError("bytes32 必须是 0x + 64 hex")
        return h[2:].lower()
    if type_name.startswith("bytes"):
        n = int(type_name[5:])
        h = str(value)
        if not h.startswith("0x"):
            raise ValueError(f"{type_name} 必须是 0x hex")
        body = h[2:]
        if len(body) != n * 2:
            raise ValueError(f"{type_name} 长度必须是 {n} 字节")
        return (body + ("00" * (32 - n))).lower()
    raise ValueError(f"不支持的类型: {type_name}")


def parse_set_items(items: List[str]) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for raw in items:
        if "=" not in raw:
            raise ValueError(f"set 格式错误: {raw}，应为 index=value")
        idx_text, val = raw.split("=", 1)
        idx = int(idx_text.strip())
        if idx < 1:
            raise ValueError("index 从 1 开始")
        out[idx] = val.strip()
    return out


def fetch_tx(args: argparse.Namespace) -> Tuple[str, int, str, str]:
    if args.tx_hash:
        rpc = ResilientRPC(
            primary_rpc=args.rpc,
            backup_rpcs=args.rpc_backup,
            timeout=args.rpc_timeout,
            max_retries=args.rpc_max_retries,
            backoff_base=args.rpc_backoff_base,
        )
        print(f"rpc_connected={rpc.ensure_connected()}")
        print(f"rpc_current={rpc.current_rpc}")
        tx = rpc.call(lambda w3: w3.eth.get_transaction(args.tx_hash))
        if tx.get("to") is None:
            raise RuntimeError("tx-hash 对应合约创建交易（to=null），模式C不支持")
        to_addr = to_checksum_address(tx["to"])
        value_wei = int(tx.get("value", 0))
        data_hex = tx.get("input", "0x")
        if isinstance(data_hex, bytes):
            data_hex = "0x" + data_hex.hex()
        source = args.tx_hash
    else:
        if not args.to or args.value_wei is None or not args.data:
            raise ValueError("不用 tx-hash 时，必须提供 --to --value-wei --data")
        print("rpc_connected=skip(manual_input_mode)")
        to_addr = to_checksum_address(args.to)
        value_wei = int(args.value_wei)
        data_hex = args.data
        source = "manual"

    data_hex = ensure_hex_data(data_hex)
    return to_addr, value_wei, data_hex, source


def cmd_preview(args: argparse.Namespace) -> None:
    to_addr, value_wei, data_hex, source = fetch_tx(args)

    selector, words = split_words(data_hex)
    types = parse_types(args.types)
    if len(types) != len(words):
        raise ValueError(
            f"types 数量({len(types)})与参数槽数量({len(words)})不一致，模式C不支持动态参数"
        )
    for t in types:
        if not is_supported_type(t):
            raise ValueError(f"不支持类型: {t}。模式C仅支持简单静态类型")

    before_vals = [decode_word(types[i], words[i]) for i in range(len(types))]
    set_map = parse_set_items(args.set_items)

    after_vals: List[Any] = []
    changed: List[ParamItem] = []
    for i, t in enumerate(types, start=1):
        before = before_vals[i - 1]
        after_raw = set_map.get(i)
        after = before if after_raw is None else decode_word(t, encode_word(t, after_raw))
        after_vals.append(after)
        if after != before:
            changed.append(ParamItem(index=i, type_name=t, before=before, after=after))

    if not changed:
        raise ValueError("未检测到任何参数修改，请用 --set index=value 指定至少一个修改")

    new_words = [encode_word(types[i], after_vals[i]) for i in range(len(types))]
    new_data = "0x" + selector + "".join(new_words)

    confirm_token = secrets.token_hex(16)
    proposal = {
        "mode": "C_no_abi_simple_static",
        "source": source,
        "txHash": args.tx_hash,
        "to": to_addr,
        "valueWei": str(value_wei),
        "types": types,
        "beforeCalldata": data_hex,
        "afterCalldata": new_data,
        "params": [
            {
                "index": p.index,
                "type": p.type_name,
                "before": str(p.before),
                "after": str(p.after),
            }
            for p in changed
        ],
        "confirmToken": confirm_token,
        "createdAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "PENDING_CONFIRM",
        "notes": "无 ABI 解析为 best-effort，仅支持简单静态类型；确认后才允许广播。",
    }

    out = args.output or f"output/log/noabi_preview_{now_ts()}.json"
    out_dir = os.path.dirname(out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(proposal, f, ensure_ascii=False, indent=2)

    print(f"proposal_file={out}")
    print("before_calldata=" + data_hex)
    print("after_calldata=" + new_data)
    print("changed_params=")
    for p in changed:
        print(f"  index={p.index} type={p.type_name} before={p.before} after={p.after}")
    print(f"confirm_token={confirm_token}")
    print("下一步需用户确认后执行：--confirm yes --confirm-token <token>")


def cmd_execute(args: argparse.Namespace) -> None:
    with open(args.proposal_file, "r", encoding="utf-8") as f:
        proposal = json.load(f)

    if proposal.get("status") != "PENDING_CONFIRM":
        raise ValueError("proposal 状态不是 PENDING_CONFIRM，禁止执行")
    if args.confirm.lower() != "yes":
        raise ValueError("必须显式传 --confirm yes")
    if args.confirm_token != proposal.get("confirmToken"):
        raise ValueError("confirm-token 不匹配，禁止执行")

    rpc = ResilientRPC(
        primary_rpc=args.rpc,
        backup_rpcs=args.rpc_backup,
        timeout=args.rpc_timeout,
        max_retries=args.rpc_max_retries,
        backoff_base=args.rpc_backoff_base,
    )
    print(f"rpc_connected={rpc.ensure_connected()}")
    print(f"rpc_current={rpc.current_rpc}")

    account = rpc.call(lambda w3: w3.eth.account.from_key(args.private_key))
    from_addr = account.address
    to_addr = to_checksum_address(proposal["to"])
    value_wei = int(proposal["valueWei"])
    data_hex = proposal["afterCalldata"]

    chain_id = int(rpc.call(lambda w3: w3.eth.chain_id))
    nonce = int(rpc.call(lambda w3: w3.eth.get_transaction_count(from_addr, "pending")))

    tx = {
        "chainId": chain_id,
        "from": from_addr,
        "to": to_addr,
        "value": value_wei,
        "data": data_hex,
        "nonce": nonce,
    }
    tx["gas"] = int(rpc.call(lambda w3: w3.eth.estimate_gas(tx)) * 1.2)
    tx["gasPrice"] = int(rpc.call(lambda w3: w3.eth.gas_price))

    signed = account.sign_transaction(tx)
    tx_hash = rpc.call(lambda w3: w3.eth.send_raw_transaction(signed.raw_transaction).hex())
    receipt = rpc.call(lambda w3: w3.eth.wait_for_transaction_receipt(tx_hash, timeout=args.receipt_timeout))

    proposal["status"] = "EXECUTED"
    proposal["executedAt"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    proposal["executedFrom"] = from_addr
    proposal["executedTxHash"] = tx_hash
    proposal["executedStatus"] = int(receipt.status)

    with open(args.proposal_file, "w", encoding="utf-8") as f:
        json.dump(proposal, f, ensure_ascii=False, indent=2)

    print(f"from={from_addr}")
    print(f"to={to_addr}")
    print(f"value_wei={value_wei}")
    print(f"tx_hash={tx_hash}")
    print(f"status={int(receipt.status)}")
    print(f"proposal_updated={args.proposal_file}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="模式C：无 ABI 的简单静态类型 calldata 修改（先预览确认，再执行广播）"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("preview", help="预览并生成确认文件，不广播")
    p1.add_argument("--rpc", required=True, help="RPC 地址")
    p1.add_argument("--tx-hash", help="可选，链上交易哈希（与 --to/--value-wei/--data 二选一）")
    p1.add_argument("--to", help="手动指定 to")
    p1.add_argument("--value-wei", type=int, help="手动指定 value（wei）")
    p1.add_argument("--data", help="手动指定 calldata")
    p1.add_argument("--types", required=True, help="参数类型列表，逗号分隔，如 address,uint256,bool")
    p1.add_argument(
        "--set-items",
        action="append",
        default=[],
        help="修改项，格式 index=value，可重复，如 --set-items 1=0xabc --set-items 2=100",
    )
    p1.add_argument("--output", help="预览输出 JSON 路径")
    add_rpc_resilience_args(p1)

    p2 = sub.add_parser("execute", help="必须确认后才广播")
    p2.add_argument("--proposal-file", required=True, help="preview 生成的 JSON 文件")
    p2.add_argument("--private-key", required=True, help="执行钱包私钥")
    p2.add_argument("--rpc", required=True, help="RPC 地址")
    p2.add_argument("--confirm", required=True, help="必须为 yes")
    p2.add_argument("--confirm-token", required=True, help="preview 阶段输出的确认令牌")
    p2.add_argument("--receipt-timeout", type=int, default=180, help="回执超时秒数")
    add_rpc_resilience_args(p2)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.cmd == "preview":
        cmd_preview(args)
        return
    if args.cmd == "execute":
        cmd_execute(args)
        return
    raise ValueError("未知子命令")


if __name__ == "__main__":
    main()
