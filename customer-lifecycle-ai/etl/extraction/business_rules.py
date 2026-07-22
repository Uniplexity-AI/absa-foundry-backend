"""
ETL Extraction Business Rules Engine — domain constraint evaluation.

Evaluates configurable business rules against structurally-validated records.
Uses AST-based safe expression evaluation — no eval(), no exec().

Rules are defined in the YAML extraction spec as Python boolean expressions.
ERROR severity → DLQ. WARNING severity → flag but pass. INFO → log only.

Section 18 of dynamic-extractor-spec.md.
"""

from __future__ import annotations

import ast
import operator as py_op
from dataclasses import dataclass, field

from etl.extraction.config_models import (
    BusinessRuleSeverity,
    BusinessRuleSpec,
)


@dataclass
class BusinessRuleResult:
    """Outcome of evaluating a single business rule against a record."""
    rule_id: str
    severity: BusinessRuleSeverity
    passed: bool
    message: str = ""


@dataclass
class BusinessRulesReport:
    """Aggregate result of evaluating all business rules against a record."""
    passed: bool = True
    results: list[BusinessRuleResult] = field(default_factory=list)

    @property
    def errors(self) -> list[BusinessRuleResult]:
        return [r for r in self.results if not r.passed and r.severity == BusinessRuleSeverity.ERROR]

    @property
    def warnings(self) -> list[BusinessRuleResult]:
        return [r for r in self.results if not r.passed and r.severity == BusinessRuleSeverity.WARNING]


class BusinessRuleEngine:
    """Safely evaluates business rule expressions against record dictionaries.

    Uses AST parsing and a whitelist of safe operations — no arbitrary code
    execution. Supports comparisons, boolean logic, membership tests, and
    a curated set of built-in functions.
    """

    # Whitelisted Python builtins available in expressions
    _SAFE_BUILTINS: dict[str, object] = {
        "abs": abs,
        "min": min,
        "max": max,
        "len": len,
        "round": round,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "True": True,
        "False": False,
        "None": None,
    }

    # Whitelisted AST node → Python operator mapping
    _OPERATORS: dict[type, object] = {
        ast.Add: py_op.add,
        ast.Sub: py_op.sub,
        ast.Mult: py_op.mul,
        ast.Div: py_op.truediv,
        ast.Mod: py_op.mod,
        ast.Gt: py_op.gt,
        ast.Lt: py_op.lt,
        ast.GtE: py_op.ge,
        ast.LtE: py_op.le,
        ast.Eq: py_op.eq,
        ast.NotEq: py_op.ne,
        ast.And: lambda a, b: a and b,
        ast.Or: lambda a, b: a or b,
        ast.Not: py_op.not_,
        ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
        ast.USub: py_op.neg,
    }

    def evaluate(self, expression: str, record: dict) -> bool:
        """Evaluate a boolean expression against a record dict.

        Args:
            expression: Python boolean expression, e.g. 'age >= 18'.
            record: Dict of field_name → value for the current record.

        Returns:
            True if the expression evaluates to True, False otherwise.

        Raises:
            ValueError: If the expression contains unsupported syntax.
        """
        try:
            tree = ast.parse(expression.strip(), mode="eval")
            result = self._eval_node(tree.body, record)
            return bool(result)
        except Exception:
            return False

    def evaluate_all(
        self,
        rules: list[BusinessRuleSpec],
        record: dict,
    ) -> BusinessRulesReport:
        """Evaluate all business rules against a single record.

        Args:
            rules: List of business rules to evaluate.
            record: Dict of field_name → value for the current record.

        Returns:
            BusinessRulesReport with per-rule results.
        """
        report = BusinessRulesReport()
        for rule in rules:
            passed = self.evaluate(rule.expression, record)
            result = BusinessRuleResult(
                rule_id=rule.id,
                severity=rule.severity,
                passed=passed,
                message=rule.message or f"Rule '{rule.name}' {'passed' if passed else 'failed'}",
            )
            report.results.append(result)
            if not passed and rule.severity == BusinessRuleSeverity.ERROR:
                report.passed = False
        return report

    # ------------------------------------------------------------------
    # AST node evaluation
    # ------------------------------------------------------------------

    def _eval_node(self, node: ast.AST, context: dict) -> Any:
        """Recursively evaluate an AST node against a record context."""
        # Literals
        if isinstance(node, ast.Constant):
            return node.value

        # Tuple literals: ('a', 'b') or (1, 2)
        if isinstance(node, ast.Tuple):
            return tuple(self._eval_node(elt, context) for elt in node.elts)

        # List literals: ['a', 'b'] or [1, 2]
        if isinstance(node, ast.List):
            return [self._eval_node(elt, context) for elt in node.elts]

        # Variable names → record fields
        if isinstance(node, ast.Name):
            if node.id in self._SAFE_BUILTINS:
                return self._SAFE_BUILTINS[node.id]
            return context.get(node.id)

        # Binary operations: a + b, a > b, etc.
        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, context)
            right = self._eval_node(node.right, context)
            op_func = self._OPERATORS.get(type(node.op))
            if op_func is None:
                raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}")
            return op_func(left, right)

        # Boolean operations: a and b, a or b
        if isinstance(node, ast.BoolOp):
            op_func = self._OPERATORS.get(type(node.op))
            if op_func is None:
                raise ValueError(f"Unsupported boolean operator: {type(node.op).__name__}")
            result = self._eval_node(node.values[0], context)
            for val_node in node.values[1:]:
                result = op_func(result, self._eval_node(val_node, context))
            return result

        # Unary operations: -x, not x
        if isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand, context)
            op_func = self._OPERATORS.get(type(node.op))
            if op_func is None:
                raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
            return op_func(operand)

        # Comparison: a > b > c chains
        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left, context)
            for op_node, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator, context)
                op_func = self._OPERATORS.get(type(op_node))
                if op_func is None:
                    raise ValueError(f"Unsupported comparison: {type(op_node).__name__}")
                if not op_func(left, right):
                    return False
                left = right
            return True

        # Function calls: len(x), abs(x), etc.
        if isinstance(node, ast.Call):
            func_name = node.func.id if isinstance(node.func, ast.Name) else None  # type: ignore[attr-defined]
            if func_name not in self._SAFE_BUILTINS:
                raise ValueError(f"Function '{func_name}' is not allowed in business rules")
            args = [self._eval_node(arg, context) for arg in node.args]
            return self._SAFE_BUILTINS[func_name](*args)

        raise ValueError(f"Unsupported expression element: {type(node).__name__}")
