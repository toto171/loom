"""Safe-eval predicate layer for runtime monitors (HANDOFF §6).

Evaluates restricted Python expressions over a ``variables`` dict — no ``eval`` /
``exec``, no builtins, no attribute/subscript access, no calls except a tiny
whitelist (``abs``/``min``/``max``). Anything else raises ``PredicateError``.

Three-valued logic: a referenced variable that is ``None`` (e.g. a dropped-out
sensor) makes ordering/arithmetic yield the ``UNAVAILABLE`` sentinel instead of
crashing on ``None < 60``. The monitor engine treats ``UNAVAILABLE`` as a
violation ("required signal unavailable"). Explicit ``is None`` checks still work.
"""
from __future__ import annotations

import ast
import operator
from typing import Any


class PredicateError(Exception):
    """A predicate is malformed or uses a disallowed construct."""


class _Unavailable:
    def __repr__(self) -> str:
        return "UNAVAILABLE"

    def __bool__(self):
        raise PredicateError("UNAVAILABLE has no boolean value")


UNAVAILABLE = _Unavailable()

_FUNCS = {"abs": abs, "min": min, "max": max}
_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_ORDER = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


def _noneify(value: Any) -> Any:
    return None if value is UNAVAILABLE else value


def _missing(value: Any) -> bool:
    return value is None or value is UNAVAILABLE


def _safe(fn, *args):
    """Apply a Python operator, converting type/zero errors into PredicateError so
    a mistyped or zero bus signal is contained rather than crashing the run."""
    try:
        return fn(*args)
    except (TypeError, ZeroDivisionError, ValueError) as exc:
        raise PredicateError(f"runtime error evaluating predicate: {exc}") from exc


def evaluate(expr: str, variables: dict[str, Any]) -> Any:
    """Evaluate ``expr`` over ``variables``; returns bool, a number, or UNAVAILABLE."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise PredicateError(f"invalid predicate {expr!r}: {exc}") from exc
    except RecursionError as exc:  # a pathologically deep expression -> contained
        raise PredicateError(f"predicate too deeply nested: {expr!r}") from exc
    try:
        return _eval(tree.body, variables)
    except RecursionError as exc:
        raise PredicateError(f"predicate too deeply nested: {expr!r}") from exc


def referenced_names(expr: str) -> set[str]:
    """Return the free variable names in ``expr`` — every ``Name`` except those in
    function-call position (so ``abs(x)`` -> {x}, but a value-position name that
    happens to equal a whitelisted function is still treated as a variable)."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise PredicateError(f"invalid predicate {expr!r}: {exc}") from exc
    except RecursionError as exc:
        raise PredicateError(f"predicate too deeply nested: {expr!r}") from exc
    call_func_ids = {
        id(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and id(node) not in call_func_ids
    }


def _eval(node: ast.AST, variables: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise PredicateError(f"unknown variable {node.id!r}")
        value = variables[node.id]
        # A dropped sensor (None) becomes UNAVAILABLE so it propagates uniformly
        # through boolean ops, equality, ordering, and arithmetic. Explicit
        # `is None` checks still work (the Compare branch _noneify-s UNAVAILABLE).
        return UNAVAILABLE if value is None else value

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            operand = _eval(node.operand, variables)
            return UNAVAILABLE if operand is UNAVAILABLE else (not operand)
        if type(node.op) in _UNARY:
            operand = _eval(node.operand, variables)
            if operand is UNAVAILABLE or operand is None:
                return UNAVAILABLE
            return _UNARY[type(node.op)](operand)
        raise PredicateError(f"unsupported unary operator {type(node.op).__name__}")

    if isinstance(node, ast.BinOp):
        if type(node.op) not in _BINOPS:
            raise PredicateError(f"unsupported operator {type(node.op).__name__}")
        left = _eval(node.left, variables)
        right = _eval(node.right, variables)
        if _missing(left) or _missing(right):
            return UNAVAILABLE
        return _safe(_BINOPS[type(node.op)], left, right)

    if isinstance(node, ast.BoolOp):
        values = [_eval(v, variables) for v in node.values]
        if isinstance(node.op, ast.And):
            if any(v is not UNAVAILABLE and not v for v in values):
                return False
            return UNAVAILABLE if any(v is UNAVAILABLE for v in values) else True
        # Or
        if any(v is not UNAVAILABLE and v for v in values):
            return True
        return UNAVAILABLE if any(v is UNAVAILABLE for v in values) else False

    if isinstance(node, ast.Compare):
        left = _eval(node.left, variables)
        for op, comparator in zip(node.ops, node.comparators, strict=True):
            right = _eval(comparator, variables)
            if isinstance(op, ast.Is):
                res = _noneify(left) is _noneify(right)
            elif isinstance(op, ast.IsNot):
                res = _noneify(left) is not _noneify(right)
            elif isinstance(op, ast.Eq):
                if left is UNAVAILABLE or right is UNAVAILABLE:
                    return UNAVAILABLE
                res = left == right
            elif isinstance(op, ast.NotEq):
                if left is UNAVAILABLE or right is UNAVAILABLE:
                    return UNAVAILABLE
                res = left != right
            elif type(op) in _ORDER:
                if _missing(left) or _missing(right):
                    return UNAVAILABLE
                res = _safe(_ORDER[type(op)], left, right)
            else:
                raise PredicateError(f"unsupported comparison {type(op).__name__}")
            if not res:
                return False
            left = right
        return True

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
            raise PredicateError("only abs/min/max calls are allowed")
        if node.keywords:
            raise PredicateError("keyword arguments are not allowed")
        args = [_eval(a, variables) for a in node.args]
        if any(_missing(a) for a in args):
            return UNAVAILABLE
        return _safe(_FUNCS[node.func.id], *args)

    raise PredicateError(f"unsupported expression: {type(node).__name__}")
