"""OTT L1.5 受限 DSL 纯函数求值器。

安全红线：客户端从网络订阅的一切内容均无任意代码执行。表达式树仅
白名单原语，资源上限硬约束（深度/调用/值大小/步数），异常统一
DslError 不暴露细节。全部原语为纯函数、无状态、无 I/O 副作用；
正则与加密原语仅做计算，网络仅由规则 request 声明发生。

用法：
    steps = [{"fn": "utf8_encode", "args": ["文本"]},
             {"fn": "sha256", "args": []}]
    run_steps(steps)  # 前一步输出作为后一步首参
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

from Crypto.Cipher import AES

from .regex_worker import _has_nested_quantifier

MAX_VALUE_BYTES = 1_048_576
MAX_DEPTH = 32
MAX_CALLS = 1000
MAX_STEPS = 8
MAX_STEP_TRANSFER_BYTES = 2 * 1_048_576
REGEX_TIMEOUT_S = 1.0
REGEX_MAX_INPUT_CHARS = 10_000
REGEX_WORKER_PATH = Path(__file__).with_name("regex_worker.py")


class DslError(Exception):
    """统一求值错误，不暴露实现细节。"""


def _value_bytes(value: Any) -> int:
    """估算值占用字节数，用于资源上限检查。"""
    if isinstance(value, str):
        return len(value.encode("utf-8", "replace"))
    if isinstance(value, bytes):
        return len(value)
    if isinstance(value, (list, dict)):
        try:
            return len(json.dumps(value).encode("utf-8"))
        except (TypeError, ValueError):
            return 0
    return 0


def _t_str(v: Any) -> str:
    if not isinstance(v, str):
        raise DslError
    return v


def _t_bytes(v: Any) -> bytes:
    if not isinstance(v, bytes):
        raise DslError
    return v


def _t_int(v: Any) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise DslError
    return v


def _t_bool(v: Any) -> bool:
    if not isinstance(v, bool):
        raise DslError
    return v


def _p_str(v: Any) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return str(v)


def _p_int(v: Any) -> int:
    if isinstance(v, bool):
        raise DslError
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        try:
            return int(v)
        except ValueError:
            raise DslError from None
    raise DslError


def _p_bool(v: Any) -> bool:
    return bool(v)


def _p_len(v: Any) -> int:
    if not isinstance(v, (str, bytes, list, dict)):
        raise DslError
    return len(v)


def _p_if(cond: Any, a: Any, b: Any) -> Any:
    return a if _t_bool(cond) else b


def _p_eq(a: Any, b: Any) -> bool:
    return a == b


def _p_not(v: Any) -> bool:
    return not _t_bool(v)


def _bin_int(fn: Callable[[int, int], int]) -> Callable[[Any, Any], int]:
    def op(a: Any, b: Any) -> int:
        return fn(_t_int(a), _t_int(b))

    return op


def _p_div(a: Any, b: Any) -> int:
    a_i, b_i = _t_int(a), _t_int(b)
    if b_i == 0:
        raise DslError
    return a_i // b_i


def _p_mod(a: Any, b: Any) -> int:
    a_i, b_i = _t_int(a), _t_int(b)
    if b_i == 0:
        raise DslError
    return a_i % b_i


def _p_bit_shift(v: Any, n: Any) -> int:
    v_i, n_i = _t_int(v), _t_int(n)
    return v_i << n_i if n_i >= 0 else v_i >> (-n_i)


def _p_now_unix() -> int:
    return int(time.time())


def _p_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _p_random_int(min_v: Any, max_v: Any) -> int:
    lo, hi = _t_int(min_v), _t_int(max_v)
    if lo > hi:
        raise DslError
    return random.randint(lo, hi)


def _regex_worker(
    pattern: str, text: str, op: str = "search", repl: str = ""
) -> str | None:
    if len(pattern) > REGEX_MAX_INPUT_CHARS or len(text) > REGEX_MAX_INPUT_CHARS:
        return None
    if _has_nested_quantifier(pattern):
        return None
    payload = json.dumps(
        {"op": op, "pattern": pattern, "text": text, "repl": repl}
    ).encode("utf-8")
    try:
        proc = subprocess.run(
            [sys.executable, str(REGEX_WORKER_PATH)],
            input=payload,
            capture_output=True,
            timeout=REGEX_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    try:
        result = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(result, dict) or not result.get("ok"):
        return None
    content = result.get("content")
    return content if isinstance(content, str) else None


def _p_regex_extract(text: Any, pattern: Any) -> str:
    text_s, pattern_s = _t_str(text), _t_str(pattern)
    result = _regex_worker(pattern_s, text_s)
    return result if result is not None else ""


def _p_regex_replace(text: Any, pattern: Any, repl: Any) -> str:
    text_s, pattern_s, repl_s = _t_str(text), _t_str(pattern), _t_str(repl)
    result = _regex_worker(pattern_s, text_s, op="replace", repl=repl_s)
    return result if result is not None else text_s


def _p_base64_encode(v: Any) -> str:
    return base64.b64encode(_t_bytes(v)).decode("ascii")


def _p_base64_decode(v: Any) -> bytes:
    return base64.b64decode(_t_str(v))


def _p_url_encode(v: Any) -> str:
    return quote(_t_str(v), safe="")


def _p_url_decode(v: Any) -> str:
    return unquote(_t_str(v))


def _p_hex_encode(v: Any) -> str:
    return _t_bytes(v).hex()


def _p_hex_decode(v: Any) -> bytes:
    try:
        return bytes.fromhex(_t_str(v))
    except ValueError:
        raise DslError from None


def _p_utf8_encode(v: Any) -> bytes:
    return _t_str(v).encode("utf-8")


def _p_utf8_decode(v: Any) -> str:
    return _t_bytes(v).decode("utf-8")


def _p_json_encode(v: Any) -> str:
    try:
        return json.dumps(v, ensure_ascii=False)
    except (TypeError, ValueError):
        raise DslError from None


def _p_json_decode(v: Any) -> Any:
    try:
        return json.loads(_t_str(v))
    except (json.JSONDecodeError, ValueError):
        raise DslError from None


def _t_dict(v: Any) -> dict:
    if not isinstance(v, dict):
        raise DslError
    return v


def _p_dict_get(d: Any, key: Any, default: Any = None) -> Any:
    return _t_dict(d).get(_t_str(key), default)


def _p_list_get(lst: Any, i: Any, default: Any = None) -> Any:
    items, idx = _t_list(lst), _t_int(i)
    return items[idx] if 0 <= idx < len(items) else default


def _t_list(v: Any) -> list:
    if not isinstance(v, list):
        raise DslError
    return v


def _p_list_len(lst: Any) -> int:
    return len(_t_list(lst))


def _p_list_join(lst: Any, sep: Any) -> str:
    items, sep_s = _t_list(lst), _t_str(sep)
    return sep_s.join(_t_str(x) for x in items)


def _p_url_join(base: Any, path: Any) -> str:
    return urljoin(_t_str(base), _t_str(path))


def _p_url_query(url: Any, key: Any) -> str:
    parsed = urlparse(_t_str(url))
    values = parse_qs(parsed.query).get(_t_str(key), [""])
    return values[0]


def _p_concat(a: Any, b: Any) -> str:
    return _t_str(a) + _t_str(b)


def _p_md5(v: Any) -> str:
    return hashlib.md5(_t_bytes(v)).hexdigest()


def _p_sha1(v: Any) -> str:
    return hashlib.sha1(_t_bytes(v)).hexdigest()


def _p_sha256(v: Any) -> str:
    return hashlib.sha256(_t_bytes(v)).hexdigest()


def _p_hmac_sha256(key: Any, msg: Any) -> str:
    return hmac.new(_t_bytes(key), _t_bytes(msg), hashlib.sha256).hexdigest()


def _zero_pad(data: bytes) -> bytes:
    pad_len = 16 - (len(data) % 16)
    return data + b"\x00" * pad_len


def _p_aes_cbc_encrypt(key: Any, iv: Any, data: Any) -> bytes:
    key_b, iv_b, data_b = _t_bytes(key), _t_bytes(iv), _t_bytes(data)
    if len(key_b) != 16 or len(iv_b) != 16:
        raise DslError
    cipher = AES.new(key_b, AES.MODE_CBC, iv_b)
    return cipher.encrypt(_zero_pad(data_b))


def _p_aes_cbc_decrypt(key: Any, iv: Any, data: Any) -> bytes:
    key_b, iv_b, data_b = _t_bytes(key), _t_bytes(iv), _t_bytes(data)
    if len(key_b) != 16 or len(iv_b) != 16:
        raise DslError
    cipher = AES.new(key_b, AES.MODE_CBC, iv_b)
    return cipher.decrypt(data_b).rstrip(b"\x00")


def _p_xor(a: Any, b: Any) -> bytes:
    a_b, b_b = _t_bytes(a), _t_bytes(b)
    return bytes(x ^ y for x, y in zip(a_b, b_b))


PRIMITIVES: dict[str, Callable[..., Any]] = {
    "str": _p_str,
    "int": _p_int,
    "bool": _p_bool,
    "len": _p_len,
    "if": _p_if,
    "eq": _p_eq,
    "not": _p_not,
    "add": _bin_int(lambda a, b: a + b),
    "sub": _bin_int(lambda a, b: a - b),
    "mul": _bin_int(lambda a, b: a * b),
    "div": _p_div,
    "mod": _p_mod,
    "bit_and": _bin_int(lambda a, b: a & b),
    "bit_or": _bin_int(lambda a, b: a | b),
    "bit_xor": _bin_int(lambda a, b: a ^ b),
    "bit_shift": _p_bit_shift,
    "now_unix": _p_now_unix,
    "now_iso": _p_now_iso,
    "random_int": _p_random_int,
    "regex_extract": _p_regex_extract,
    "regex_replace": _p_regex_replace,
    "base64_encode": _p_base64_encode,
    "base64_decode": _p_base64_decode,
    "url_encode": _p_url_encode,
    "url_decode": _p_url_decode,
    "hex_encode": _p_hex_encode,
    "hex_decode": _p_hex_decode,
    "utf8_encode": _p_utf8_encode,
    "utf8_decode": _p_utf8_decode,
    "json_encode": _p_json_encode,
    "json_decode": _p_json_decode,
    "dict_get": _p_dict_get,
    "list_get": _p_list_get,
    "list_len": _p_list_len,
    "list_join": _p_list_join,
    "url_join": _p_url_join,
    "url_query": _p_url_query,
    "concat": _p_concat,
    "md5": _p_md5,
    "sha1": _p_sha1,
    "sha256": _p_sha256,
    "hmac_sha256": _p_hmac_sha256,
    "aes_cbc_encrypt": _p_aes_cbc_encrypt,
    "aes_cbc_decrypt": _p_aes_cbc_decrypt,
    "xor": _p_xor,
}


class _Budget:
    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls = 0

    def spend(self) -> None:
        self.calls += 1
        if self.calls > MAX_CALLS:
            raise DslError


def _evaluate(expr: Any, budget: _Budget, depth: int = 0) -> Any:
    if depth > MAX_DEPTH:
        raise DslError
    if not isinstance(expr, dict) or "fn" not in expr:
        return expr
    budget.spend()
    fn = expr["fn"]
    if not isinstance(fn, str) or fn not in PRIMITIVES:
        raise DslError
    args = expr.get("args", [])
    if not isinstance(args, list):
        raise DslError
    values = [_evaluate(a, budget, depth + 1) for a in args]
    try:
        result = PRIMITIVES[fn](*values)
    except DslError:
        raise
    except Exception:
        raise DslError from None
    if _value_bytes(result) > MAX_VALUE_BYTES:
        raise DslError
    return result


def evaluate(expr: Any) -> Any:
    """求值单个表达式树；字面量原样返回。"""
    return _evaluate(expr, _Budget())


def run_steps(steps: Any, initial: Any = None) -> Any:
    """顺序管道：前一步输出作为后一步首参。返回末步结果。"""
    if not isinstance(steps, list) or not steps:
        raise DslError
    if len(steps) > MAX_STEPS:
        raise DslError
    budget = _Budget()
    result = initial
    transferred = _value_bytes(initial) if initial is not None else 0
    for step in steps:
        if (
            not isinstance(step, dict)
            or "fn" not in step
            or not isinstance(step["fn"], str)
        ):
            raise DslError
        args = step.get("args", [])
        if not isinstance(args, list):
            raise DslError
        args = [result] + args if result is not None else args
        result = _evaluate({"fn": step["fn"], "args": args}, budget)
        transferred += _value_bytes(result)
        if transferred > MAX_STEP_TRANSFER_BYTES:
            raise DslError
    return result
