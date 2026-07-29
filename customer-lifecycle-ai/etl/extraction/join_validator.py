"""Pre-query validation for physical-table and pre-aggregation CTE joins."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy import MetaData, inspect

from etl.extraction.config_models import ExtractionConfigSpec, PreAggregationSpec

logger = logging.getLogger("etl.extraction.join_validator")


@dataclass
class JoinValidationReport:
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class JoinValidator:
    """Validate join aliases, source columns, and physical-table indexes.

    Pre-aggregation CTEs are virtual relations: they are not looked up as
    database tables, but their emitted group-by and aggregate columns are
    validated against the extraction spec.
    """

    def __init__(self, engine: sa.Engine, metadata: MetaData) -> None:
        self._inspector = inspect(engine)

    def validate(self, config: ExtractionConfigSpec) -> JoinValidationReport:
        report = JoinValidationReport()
        self._check_table(config.primary_entity.table, "primary_entity", report)

        aliases = {config.primary_entity.alias: config.primary_entity.table}
        ctes = {cte.alias: cte for cte in config.pre_aggregations}
        cte_names = {cte.name for cte in config.pre_aggregations}

        for join in config.joins:
            if join.alias in aliases:
                report.errors.append(f"Duplicate alias '{join.alias}' in join to '{join.table}'")
                continue
            if join.table in cte_names:
                if join.alias not in ctes or ctes[join.alias].name != join.table:
                    report.errors.append(
                        f"CTE '{join.table}' must be joined using its declared alias"
                    )
            else:
                self._check_table(join.table, f"join '{join.alias}'", report)

            for condition in join.on:
                self._check_condition(condition.left, condition.right, aliases, ctes, report)

            if join.table not in cte_names:
                self._check_join_indexes(join, report)
            aliases[join.alias] = join.table

        report.is_valid = not report.errors
        if report.warnings:
            logger.warning("Join validation: %d warning(s) — %s", len(report.warnings), report.warnings[0] if len(report.warnings) == 1 else f"{len(report.warnings)} issues")
        return report

    def _check_table(self, table_ref: str, context: str, report: JoinValidationReport) -> None:
        schema, table = self._split_table(table_ref)
        if schema not in self._inspector.get_schema_names():
            report.errors.append(f"[{context}] Schema '{schema}' does not exist")
            return
        if table not in self._inspector.get_table_names(schema=schema):
            report.errors.append(f"[{context}] Table '{schema}.{table}' does not exist")

    def _check_condition(
        self,
        left: str,
        right: str,
        aliases: dict[str, str],
        ctes: dict[str, PreAggregationSpec],
        report: JoinValidationReport,
    ) -> None:
        left_type = self._column_type(left, aliases, ctes, report)
        right_type = self._column_type(right, aliases, ctes, report)
        if left_type and right_type and not self._types_compatible(left_type, right_type):
            report.warnings.append(
                f"Join type mismatch: '{left}' ({left_type}) vs '{right}' ({right_type})"
            )

    def _column_type(
        self,
        reference: str,
        aliases: dict[str, str],
        ctes: dict[str, PreAggregationSpec],
        report: JoinValidationReport,
    ) -> str | None:
        try:
            alias, column = reference.split(".")
        except ValueError:
            report.errors.append(f"Invalid column reference '{reference}' — expected 'alias.column'")
            return None

        if alias in ctes:
            cte = ctes[alias]
            grouped = {field.rsplit(".", 1)[-1] for field in cte.group_by}
            aggregated = {aggregation.alias for aggregation in cte.aggregations}
            if column not in grouped | aggregated:
                report.errors.append(f"CTE '{cte.name}' does not emit column '{column}'")
            # Aggregate types are database-specific. Type comparison is skipped.
            if column in aggregated:
                return None
            table_ref = cte.from_table
        else:
            table_ref = aliases.get(alias)
            if table_ref is None:
                report.errors.append(f"Unknown or forward-referenced alias '{alias}'")
                return None

        schema, table = self._split_table(table_ref)
        try:
            columns = self._inspector.get_columns(table_name=table, schema=schema)
        except Exception as exc:
            report.errors.append(f"Cannot inspect '{schema}.{table}': {exc}")
            return None
        for item in columns:
            if item["name"] == column:
                return str(item["type"]).lower()
        report.errors.append(f"Column '{column}' not found in '{schema}.{table}'")
        return None

    def _check_join_indexes(self, join, report: JoinValidationReport) -> None:
        schema, table = self._split_table(join.table)
        try:
            indexes = self._inspector.get_indexes(table_name=table, schema=schema)
        except Exception:
            return
        indexed = {column for index in indexes for column in index.get("column_names", [])}
        for condition in join.on:
            for reference in (condition.left, condition.right):
                alias, column = reference.split(".", 1)
                if alias == join.alias and column not in indexed:
                    report.warnings.append(
                        f"Join column '{reference}' has no index on '{schema}.{table}'"
                    )

    @staticmethod
    def _split_table(reference: str) -> tuple[str, str]:
        parts = reference.split(".")
        return (parts[0], parts[1]) if len(parts) == 2 else ("public", parts[0])

    @staticmethod
    def _types_compatible(left: str, right: str) -> bool:
        families = (
            {"integer", "bigint", "smallint", "serial", "bigserial"},
            {"real", "double precision", "numeric", "decimal", "float"},
            {"character varying", "varchar", "char", "character", "text", "uuid"},
            {"date", "timestamp without time zone", "timestamp with time zone", "datetime"},
            {"boolean", "bool"},
        )
        return left == right or any(left in family and right in family for family in families)
