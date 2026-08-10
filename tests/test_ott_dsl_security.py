"""OTT L1.5 DSL 组合安全与资源上限测试（Phase 1.5）。"""

import random
from typing import Any

import pytest

from src.backend.integration.ott_dsl import (
    DslError,
    MAX_STEP_TRANSFER_BYTES,
    MAX_VALUE_BYTES,
    evaluate,
    run_steps,
)


@pytest.mark.parametrize(
    "expr",
    [
        {"fn": "add", "args": [{"fn": "evil", "args": []}, 1]},
        {"fn": "add", "args": [1]},
        {"fn": "str", "args": "x"},
        {"fn": "str", "args": None},
        {"fn": 1, "args": []},
        {"fn": "div", "args": [1, 0]},
        {"fn": "bit_shift", "args": [1, 10**9]},
        {"fn": "json_decode", "args": ["[" * 100000 + "]" * 100000]},
    ],
)
def test_combination_matrix_never_escapes_dsl_error(expr: Any) -> None:
    with pytest.raises(DslError):
        evaluate(expr)


def test_huge_int_literal_rejected() -> None:
    with pytest.raises(DslError):
        evaluate(2 ** (MAX_VALUE_BYTES * 8 + 8))


def test_huge_int_result_rejected() -> None:
    with pytest.raises(DslError):
        evaluate({"fn": "mul", "args": [2**5000000, 2**5000000]})


def test_step_transfer_limit() -> None:
    with pytest.raises(DslError):
        run_steps(
            [{"fn": "concat", "args": ["b"]}],
            initial="a" * (MAX_STEP_TRANSFER_BYTES + 1),
        )


def test_fuzz_random_expressions_only_dsl_error_or_success() -> None:
    rng = random.Random(20260808)
    fns = [
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
        "concat",
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
        "md5",
        "sha1",
        "sha256",
        "xor",
    ]
    literals = [0, 1, -1, 2, "", "a", "abc", True, False, b"x", [], {}]

    def _expr(depth: int) -> Any:
        if depth <= 0 or rng.random() < 0.4:
            return rng.choice(literals)
        fn = rng.choice(fns)
        arity = rng.randint(0, 3)
        return {"fn": fn, "args": [_expr(depth - 1) for _ in range(arity)]}

    for _ in range(300):
        expr = _expr(4)
        try:
            evaluate(expr)
        except DslError:
            pass
