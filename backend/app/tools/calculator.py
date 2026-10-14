from __future__ import annotations

import ast
import math
import operator
import statistics
from typing import Literal

_SAFE_NAMES: dict[str, object] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
}

_ALLOWED_OPS = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.UAdd,
    ast.USub,
)

_MAX_EXPONENT = 1_000


def _safe_eval(expr: str) -> float:
    if len(expr) > 200:
        raise ValueError("Expression exceeds 200 characters.")

    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Syntax error in expression: {exc}") from exc

    def _visit(node: ast.expr) -> float:
        if isinstance(node, ast.Expression):
            return _visit(node.body)
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)):
                raise ValueError(f"Non-numeric constant: {node.value!r}")
            return float(node.value)
        if isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, (ast.UAdd, ast.USub)):
                raise ValueError(f"Disallowed unary operator: {type(node.op).__name__}")
            val = _visit(node.operand)
            return -val if isinstance(node.op, ast.USub) else val
        if isinstance(node, ast.BinOp):
            if not isinstance(node.op, _ALLOWED_OPS):
                raise ValueError(f"Disallowed operator: {type(node.op).__name__}")
            left = _visit(node.left)
            right = _visit(node.right)
            if isinstance(node.op, ast.Div):
                if right == 0:
                    raise ZeroDivisionError("Division by zero.")
                return left / right
            if isinstance(node.op, ast.FloorDiv):
                if right == 0:
                    raise ZeroDivisionError("Division by zero.")
                return float(left // right)
            if isinstance(node.op, ast.Mod):
                if right == 0:
                    raise ZeroDivisionError("Modulo by zero.")
                return float(left % right)
            if isinstance(node.op, ast.Pow):
                if abs(right) > _MAX_EXPONENT:
                    raise ValueError(
                        f"Exponent magnitude {abs(right)} exceeds limit {_MAX_EXPONENT}."
                    )
                result = left**right
                if math.isnan(result) or math.isinf(result):
                    raise OverflowError("Result is infinite or NaN.")
                return float(result)
            ops_map = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
            }
            result = ops_map[type(node.op)](left, right)
            if math.isnan(result) or math.isinf(result):
                raise OverflowError("Result is infinite or NaN.")
            return float(result)
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError("Attribute calls are not allowed.")
            name = node.func.id
            if name not in _SAFE_NAMES:
                raise ValueError(
                    f"Function '{name}' is not allowed. "
                    f"Allowed functions: {', '.join(sorted(_SAFE_NAMES))}."
                )
            args = [_visit(a) for a in node.args]
            if name == "round" and len(args) == 2:
                return float(round(args[0], int(args[1])))
            return float(_SAFE_NAMES[name](*args))
        if isinstance(node, ast.Name):
            raise ValueError(
                f"Variable name '{node.id}' is not allowed in expressions. "
                "Use numeric literals only."
            )
        if isinstance(node, ast.Attribute):
            raise ValueError("Attribute access is not allowed in expressions.")
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")

    return _visit(tree)


def run_calculator(
    operation: Literal[
        "expression", "sum", "mean", "median", "min", "max", "stdev", "percent_change"
    ],
    expression: str | None = None,
    values: list[float] | None = None,
) -> str:
    try:
        if operation == "expression":
            if not expression:
                return "Error: 'expression' field is required for operation 'expression'."
            result = _safe_eval(expression)
            return f"Result: {result}"

        if not values:
            return f"Error: 'values' field is required for operation '{operation}'."

        if operation == "sum":
            return f"Result: {sum(values)}"
        if operation == "mean":
            return f"Result: {statistics.mean(values)}"
        if operation == "median":
            return f"Result: {statistics.median(values)}"
        if operation == "min":
            return f"Result: {min(values)}"
        if operation == "max":
            return f"Result: {max(values)}"
        if operation == "stdev":
            if len(values) < 2:
                return "Error: Standard deviation requires at least 2 values."
            return f"Result: {statistics.stdev(values)}"
        if operation == "percent_change":
            if len(values) != 2:
                return "Error: 'percent_change' requires exactly 2 values: [old_value, new_value]."
            old, new = values
            if old == 0:
                return "Error: Cannot compute percent change when the old value is 0 (division by zero)."
            change = (new - old) / old * 100
            return f"Result: {change:.4f}% change from {old} to {new}"

        return f"Error: Unknown operation '{operation}'."

    except ZeroDivisionError as exc:
        return f"Error: {exc}"
    except OverflowError as exc:
        return f"Error: Arithmetic overflow: {exc}"
    except ValueError as exc:
        return f"Error: {exc}"
    except statistics.StatisticsError as exc:
        return f"Error: Statistics error: {exc}"
    except Exception as exc:
        return f"Error: Unexpected calculator error: {exc}"
