"""Business Rules Engine — deterministic banking logic.

Evaluates YAML-configured banking rules AFTER eligibility checks.
Conditions are parsed with a safe AST-based evaluator — NO eval().
"""
from __future__ import annotations

import ast
import logging
import re
from pathlib import Path

import yaml

from app.schemas.schemas import DecisionContext, PolicyResult

logger = logging.getLogger("decision.business_rules")

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "policies"
_CATALOG_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "candidates"


def _load_action_categories() -> dict[str, set[str]]:
    """Load action category membership from YAML action catalog."""
    path = _CATALOG_DIR / "action_catalog.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    return {k: set(v) for k, v in data.get("actions", {}).items()}


# Load once at module level
_action_categories = _load_action_categories()
RETENTION_ACTIONS = _action_categories.get("retention", set())
CROSS_SELL_ACTIONS = _action_categories.get("cross_sell", set())
ENGAGEMENT_ACTIONS = _action_categories.get("engagement", set())


# ===========================================================================
# Safe Expression Evaluator (AST-based — replaces eval())
# ===========================================================================

class _ExpressionEvaluator(ast.NodeVisitor):
    """Safely evaluate a condition string against a DecisionContext.

    Only allows: comparisons, BooleanOps, attribute access on 'context',
    constants (str, int, float, bool, None, list).
    Explicitly REJECTS: calls, subscript, lambda, generators, imports.
    """

    ALLOWED_NODES = {
        ast.Expression, ast.Compare, ast.BoolOp, ast.UnaryOp, ast.Not,
        ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
        ast.In, ast.NotIn, ast.And, ast.Or,
        ast.Name, ast.Attribute, ast.Constant, ast.List,
        ast.Load, ast.Or, ast.And,
    }

    def __init__(self, context: DecisionContext, ns: dict):
        self._context = context
        self._ns = ns

    def evaluate(self, expression: str) -> bool:
        try:
            tree = ast.parse(expression.strip(), mode="eval")
            self._check_safety(tree)
            return bool(self.visit(tree.body))
        except _UnsafeExpression as e:
            logger.warning("Unsafe expression rejected: %s — %s", expression[:80], e)
            return False
        except Exception as e:
            logger.warning("Expression eval failed: %s — %s: %s", expression[:80], type(e).__name__, e)
            return False

    def _check_safety(self, node: ast.AST) -> None:
        """Recursively check that every node type is allowed."""
        if type(node) not in self.ALLOWED_NODES:
            raise _UnsafeExpression(f"Forbidden node: {type(node).__name__}")
        for child in ast.iter_child_nodes(node):
            self._check_safety(child)

    def visit_Compare(self, node: ast.Compare) -> bool:
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            if isinstance(op, ast.Eq):       result = left == right
            elif isinstance(op, ast.NotEq):  result = left != right
            elif isinstance(op, ast.Lt):     result = left < right
            elif isinstance(op, ast.LtE):    result = left <= right
            elif isinstance(op, ast.Gt):     result = left > right
            elif isinstance(op, ast.GtE):    result = left >= right
            elif isinstance(op, ast.In):     result = left in right
            elif isinstance(op, ast.NotIn):  result = left not in right
            else: raise _UnsafeExpression(f"Unknown comparison operator: {type(op).__name__}")
            if not result:
                return False
        return True

    def visit_BoolOp(self, node: ast.BoolOp) -> object:
        if isinstance(node.op, ast.And):
            result = self.visit(node.values[0])
            for v in node.values[1:]:
                if not result:
                    return result
                result = self.visit(v)
            return result
        elif isinstance(node.op, ast.Or):
            for v in node.values:
                result = self.visit(v)
                if result:
                    return result
            return result
        raise _UnsafeExpression(f"Unknown bool op: {type(node.op).__name__}")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> bool:
        if isinstance(node.op, ast.Not):
            return not self.visit(node.operand)
        raise _UnsafeExpression(f"Unknown unary op: {type(node.op).__name__}")

    def visit_Attribute(self, node: ast.Attribute) -> object:
        obj = self.visit(node.value)
        return getattr(obj, node.attr)

    def visit_Name(self, node: ast.Name) -> object:
        if node.id == "context":
            return self._context
        if node.id in self._ns:
            return self._ns[node.id]
        raise _UnsafeExpression(f"Unknown name: {node.id}")

    def visit_Constant(self, node: ast.Constant) -> object:
        return node.value

    def visit_List(self, node: ast.List) -> list:
        return [self.visit(e) for e in node.elts]

    def generic_visit(self, node: ast.AST) -> object:
        raise _UnsafeExpression(f"Unhandled node: {type(node).__name__}")


class _UnsafeExpression(Exception):
    """Raised when an expression contains a forbidden AST node."""
    pass


# ===========================================================================
# Business Rules Engine
# ===========================================================================

class BusinessRulesEngine:
    """Applies deterministic banking logic to the decision pipeline."""

    def __init__(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(_CONFIG_DIR / "banking_rules.yaml")
        self._rules = self._load_rules(config_path)
        logger.info("BusinessRulesEngine loaded: %d rules", len(self._rules))

    def apply(self, context: DecisionContext) -> PolicyResult:
        """Evaluate all business rules against the context."""
        blocked: list[str] = []
        required: list[str] = []
        modifiers: dict = {}
        triggered: list[str] = []

        for rule in self._rules:
            if self._evaluate_condition(rule["condition"], context):
                triggered.append(rule["id"])
                action = rule["action"]
                severity = rule.get("severity", "HARD")

                if action == "ONLY_REACTIVATION":
                    blocked.extend(CROSS_SELL_ACTIONS)
                    blocked.extend(ENGAGEMENT_ACTIONS)
                elif action == "NO_MARKETING":
                    blocked.extend(CROSS_SELL_ACTIONS)
                    blocked.extend(ENGAGEMENT_ACTIONS)
                elif action == "PRIORITIZE_RETENTION":
                    for a in RETENTION_ACTIONS:
                        modifiers[a] = modifiers.get(a, 1.0) * 1.5
                elif action == "PRIORITIZE_CROSS_SELL":
                    for a in CROSS_SELL_ACTIONS:
                        modifiers[a] = modifiers.get(a, 1.0) * 1.5
                elif action == "PRIORITIZE_DIGITAL":
                    for a in ENGAGEMENT_ACTIONS:
                        modifiers[a] = modifiers.get(a, 1.0) * 1.5
                elif action == "REDUCE_OUTBOUND":
                    modifiers["_global"] = 0.5
                elif action == "ESCALATE_TO_RM":
                    required.append("RM_CALL")
                elif action == "REMOVE_CANDIDATE":
                    blocked.append("_duplicate_product")

        return PolicyResult(
            blocked_actions=list(set(blocked)),
            required_actions=list(set(required)),
            priority_modifiers=modifiers,
            triggered_rules=triggered,
        )

    def _evaluate_condition(self, condition: str, context: DecisionContext) -> bool:
        """Safely evaluate a condition string using AST parsing.

        Supports: AND, OR, ==, !=, in, not in, >, <, >=, <=
        with attribute access via 'context.field'.
        No eval() — uses Python's ast module for safe evaluation.
        """
        # Normalize AND/OR to Python keywords
        expr = re.sub(r'\bAND\b', 'and', condition)
        expr = re.sub(r'\bOR\b', 'or', expr)

        ns = {"True": True, "False": False, "None": None}
        evaluator = _ExpressionEvaluator(context, ns)
        return evaluator.evaluate(expr)

    def _load_rules(self, config_path: str) -> list[dict]:
        with open(config_path) as f:
            data = yaml.safe_load(f)
        return data.get("rules", [])

    def reload(self, config_path: str | None = None) -> None:
        if config_path is None:
            config_path = str(_CONFIG_DIR / "banking_rules.yaml")
        self._rules = self._load_rules(config_path)
        logger.info("BusinessRulesEngine reloaded: %d rules", len(self._rules))
