"""OTT L1.5 DSL 纯函数求值器测试。"""

from __future__ import annotations

import time

import pytest

from src.backend.integration.ott_dsl import (
    DslError,
    MAX_CALLS,
    MAX_DEPTH,
    MAX_STEPS,
    MAX_VALUE_BYTES,
    PRIMITIVES,
    evaluate,
    run_steps,
)


class TestBasicPrimitives:
    def test_value_primitives(self) -> None:
        assert evaluate({"fn": "str", "args": [42]}) == "42"
        assert evaluate({"fn": "int", "args": ["42"]}) == 42
        assert evaluate({"fn": "bool", "args": [1]}) is True
        assert evaluate({"fn": "len", "args": ["abc"]}) == 3

    def test_arithmetic(self) -> None:
        assert evaluate({"fn": "add", "args": [1, 2]}) == 3
        assert evaluate({"fn": "sub", "args": [5, 3]}) == 2
        assert evaluate({"fn": "mul", "args": [3, 4]}) == 12
        assert evaluate({"fn": "div", "args": [7, 2]}) == 3
        assert evaluate({"fn": "mod", "args": [7, 2]}) == 1
        assert evaluate({"fn": "bit_and", "args": [6, 3]}) == 2
        assert evaluate({"fn": "bit_or", "args": [4, 1]}) == 5
        assert evaluate({"fn": "bit_xor", "args": [6, 3]}) == 5
        assert evaluate({"fn": "bit_shift", "args": [1, 4]}) == 16
        assert evaluate({"fn": "bit_shift", "args": [16, -2]}) == 4

    def test_control(self) -> None:
        assert evaluate({"fn": "if", "args": [True, "a", "b"]}) == "a"
        assert evaluate({"fn": "if", "args": [False, "a", "b"]}) == "b"
        assert evaluate({"fn": "eq", "args": [1, 1]}) is True
        assert evaluate({"fn": "eq", "args": ["a", "b"]}) is False
        assert evaluate({"fn": "not", "args": [True]}) is False

    def test_nested_expression(self) -> None:
        expr = {"fn": "add", "args": [1, {"fn": "mul", "args": [2, 3]}]}
        assert evaluate(expr) == 7

    def test_literal_passthrough(self) -> None:
        assert evaluate(42) == 42
        assert evaluate("text") == "text"


class TestEncodingPrimitives:
    def test_base64_roundtrip(self) -> None:
        expr = {
            "fn": "base64_decode",
            "args": [{"fn": "base64_encode", "args": [b"hello"]}],
        }
        assert evaluate(expr) == b"hello"

    def test_hex_roundtrip(self) -> None:
        expr = {
            "fn": "hex_decode",
            "args": [{"fn": "hex_encode", "args": [b"\x01\x02"]}],
        }
        assert evaluate(expr) == b"\x01\x02"

    def test_utf8_roundtrip(self) -> None:
        expr = {"fn": "utf8_decode", "args": [{"fn": "utf8_encode", "args": ["中文"]}]}
        assert evaluate(expr) == "中文"

    def test_url_encode_decode(self) -> None:
        assert evaluate({"fn": "url_encode", "args": ["a b&c"]}) == "a%20b%26c"
        assert evaluate({"fn": "url_decode", "args": ["a%20b"]}) == "a b"

    def test_json_roundtrip(self) -> None:
        expr = {
            "fn": "json_decode",
            "args": [{"fn": "json_encode", "args": [{"k": "v"}]}],
        }
        assert evaluate(expr) == {"k": "v"}


class TestCollectionPrimitives:
    def test_dict_get(self) -> None:
        assert evaluate({"fn": "dict_get", "args": [{"a": 1}, "a"]}) == 1
        assert evaluate({"fn": "dict_get", "args": [{"a": 1}, "b", "dflt"]}) == "dflt"

    def test_list_ops(self) -> None:
        assert evaluate({"fn": "list_get", "args": [[10, 20], 1]}) == 20
        assert evaluate({"fn": "list_get", "args": [[10], 5, -1]}) == -1
        assert evaluate({"fn": "list_len", "args": [[1, 2, 3]]}) == 3
        assert evaluate({"fn": "list_join", "args": [["a", "b"], "-"]}) == "a-b"

    def test_url_join_query(self) -> None:
        assert (
            evaluate({"fn": "url_join", "args": ["https://x.com/a", "b"]})
            == "https://x.com/b"
        )
        assert evaluate({"fn": "url_query", "args": ["https://x.com/?k=v", "k"]}) == "v"

    def test_concat(self) -> None:
        assert evaluate({"fn": "concat", "args": ["a", "b"]}) == "ab"


class TestTimeRandomPrimitives:
    def test_now_unix(self) -> None:
        before = int(time.time())
        now = evaluate({"fn": "now_unix", "args": []})
        after = int(time.time())
        assert before <= now <= after

    def test_now_iso(self) -> None:
        iso = evaluate({"fn": "now_iso", "args": []})
        assert "T" in iso and iso.endswith("+00:00")

    def test_random_int_bounds(self) -> None:
        for _ in range(20):
            v = evaluate({"fn": "random_int", "args": [5, 7]})
            assert 5 <= v <= 7


class TestRegexPrimitives:
    def test_regex_extract(self) -> None:
        expr = {"fn": "regex_extract", "args": ["<h1>Hi</h1>", "<h1>(.*?)</h1>"]}
        assert evaluate(expr) == "Hi"

    def test_regex_replace(self) -> None:
        expr = {"fn": "regex_replace", "args": ["a1b2", r"\d", "x"]}
        assert evaluate(expr) == "axbx"

    def test_regex_malicious_returns_fast(self) -> None:
        # 嵌套量词静态拒绝，1s 内返回空
        start = time.monotonic()
        expr = {"fn": "regex_extract", "args": ["a" * 9000, "(a+)+$"]}
        assert evaluate(expr) == ""
        assert time.monotonic() - start < 1.0


class TestCryptoPrimitives:
    def test_digests(self) -> None:
        assert (
            evaluate({"fn": "md5", "args": [b"abc"]})
            == "900150983cd24fb0d6963f7d28e17f72"
        )
        assert (
            evaluate({"fn": "sha1", "args": [b"abc"]})
            == "a9993e364706816aba3e25717850c26c9cd0d89d"
        )
        assert evaluate({"fn": "sha256", "args": [b"abc"]}) == (
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )

    def test_hmac_sha256(self) -> None:
        result = evaluate({"fn": "hmac_sha256", "args": [b"key", b"msg"]})
        assert (
            result == "2d93cbc1be167bcb1637a4a23cbff01a7878f0c50ee833954ea5221bb1b8c628"
        )

    def test_aes_cbc_roundtrip(self) -> None:
        # 与现网 crypt.py 相同参数（AES-128-CBC + ZeroPadding）
        key, iv = b"c9ec834c80f77237", b"db4d6bfde3057dca"
        enc = {"fn": "aes_cbc_encrypt", "args": [key, iv, b"Hello World!"]}
        encrypted = evaluate(enc)
        dec = {"fn": "aes_cbc_decrypt", "args": [key, iv, encrypted]}
        assert evaluate(dec) == b"Hello World!"

    def test_xor(self) -> None:
        assert (
            evaluate({"fn": "xor", "args": [b"\x01\x02", b"\xff\x00"]}) == b"\xfe\x02"
        )


class TestConstraints:
    def test_unknown_primitive_rejected(self) -> None:
        with pytest.raises(DslError):
            evaluate({"fn": "evil", "args": []})

    def test_type_mismatch_rejected(self) -> None:
        with pytest.raises(DslError):
            evaluate({"fn": "add", "args": ["a", "b"]})
        with pytest.raises(DslError):
            evaluate({"fn": "len", "args": [42]})

    def test_divide_by_zero_rejected(self) -> None:
        with pytest.raises(DslError):
            evaluate({"fn": "div", "args": [1, 0]})
        with pytest.raises(DslError):
            evaluate({"fn": "mod", "args": [1, 0]})

    def test_depth_limit(self) -> None:
        expr = {"fn": "str", "args": [0]}
        for _ in range(MAX_DEPTH + 2):
            expr = {"fn": "str", "args": [expr]}
        with pytest.raises(DslError):
            evaluate(expr)

    def test_call_limit(self) -> None:
        # 深度受限的链式调用，调用数远超 MAX_CALLS
        expr: object = 1
        for _ in range(MAX_CALLS + 10):
            expr = {"fn": "add", "args": [expr, 1]}
        with pytest.raises(DslError):
            evaluate(expr)

    def test_value_size_limit(self) -> None:
        big = "x" * (MAX_VALUE_BYTES + 10)
        with pytest.raises(DslError):
            evaluate({"fn": "str", "args": [big]})

    def test_error_hides_details(self) -> None:
        with pytest.raises(DslError) as exc:
            evaluate({"fn": "dict_get", "args": ["notdict", "k"]})
        assert str(exc.value) == ""
        assert "DslError" not in ""


class TestRunSteps:
    def test_pipeline_chain(self) -> None:
        # 前一步输出作为后一步首参：utf8_encode("abc") → sha256
        steps = [
            {"fn": "utf8_encode", "args": ["abc"]},
            {"fn": "sha256", "args": []},
        ]
        result = run_steps(steps)
        assert (
            result == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )

    def test_pipeline_initial_value(self) -> None:
        steps = [{"fn": "concat", "args": ["!"]}, {"fn": "concat", "args": ["?"]}]
        assert run_steps(steps, initial="a") == "a!?"

    def test_steps_limit(self) -> None:
        steps = [{"fn": "str", "args": [1]} for _ in range(MAX_STEPS + 1)]
        with pytest.raises(DslError):
            run_steps(steps)

    def test_empty_steps_rejected(self) -> None:
        with pytest.raises(DslError):
            run_steps([])

    def test_jisubei_style_aes_request(self) -> None:
        # 极速杯式请求体：base64_encode(aes_cbc_encrypt(key, iv, utf8_encode(str(now_unix()))))
        expr = {
            "fn": "base64_encode",
            "args": [
                {
                    "fn": "aes_cbc_encrypt",
                    "args": [
                        b"c9ec834c80f77237",
                        b"db4d6bfde3057dca",
                        {
                            "fn": "utf8_encode",
                            "args": [
                                {"fn": "str", "args": [{"fn": "now_unix", "args": []}]}
                            ],
                        },
                    ],
                }
            ],
        }
        result = evaluate(expr)
        assert isinstance(result, str) and len(result) > 20


class TestPrimitiveRegistry:
    def test_required_primitives_present(self) -> None:
        required = {
            "str",
            "int",
            "bool",
            "len",
            "if",
            "eq",
            "not",
            "add",
            "sub",
            "mul",
            "div",
            "mod",
            "bit_and",
            "bit_or",
            "bit_xor",
            "bit_shift",
            "now_unix",
            "now_iso",
            "random_int",
            "regex_extract",
            "regex_replace",
            "base64_encode",
            "base64_decode",
            "url_encode",
            "url_decode",
            "hex_encode",
            "hex_decode",
            "utf8_encode",
            "utf8_decode",
            "json_encode",
            "json_decode",
            "dict_get",
            "list_get",
            "list_len",
            "list_join",
            "url_join",
            "url_query",
            "concat",
            "md5",
            "sha1",
            "sha256",
            "hmac_sha256",
            "aes_cbc_encrypt",
            "aes_cbc_decrypt",
            "xor",
        }
        assert required <= set(PRIMITIVES)
