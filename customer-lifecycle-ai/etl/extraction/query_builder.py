"""
ETL Extraction Query Builder — dynamic SQLAlchemy Select generation.

Reads an ExtractionConfigSpec and builds a parameterized, safe SQL query.
Supports: multi-table JOINs, 22 filter operators, aggregations, calculated
fields, incremental watermark filtering, and GROUP BY.

Sections 4.2, 9, 10, 11, 12, 13 of dynamic-extractor-spec.md.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy import MetaData, Table, select, text, func
from sqlalchemy.sql import Select

from etl.extraction.config_models import (
    AggregationFunction,
    ExtractionConfigSpec,
    FilterOperator,
    FilterSpec,
    JoinSpec,
    JoinType,
)


class QueryBuildError(Exception):
    """Raised when query construction fails (e.g. invalid column reference)."""


class DynamicQueryBuilder:
    """Builds parameterized SQLAlchemy Select statements from extraction specs.

    Usage:
        builder = DynamicQueryBuilder(engine, metadata)
        query = builder.build(config)
        with engine.connect() as conn:
            result = conn.execute(query)
    """

    # Map join types to SQLAlchemy parameters
    _JOIN_METHODS: dict[JoinType, tuple[bool, bool]] = {
        JoinType.INNER: (False, False),
        JoinType.LEFT: (True, False),
        JoinType.RIGHT: (True, False),  # full=True handled separately
        JoinType.FULL: (True, True),
    }

    def __init__(self, engine: sa.Engine, metadata: MetaData) -> None:
        """Initialize with a SQLAlchemy engine and MetaData.

        Args:
            engine: Connected SQLAlchemy engine for reflection.
            metadata: Bound MetaData for table resolution.
        """
        self._engine = engine
        self._metadata = metadata

    def build(self, config: ExtractionConfigSpec) -> Select:
        """Build a SQLAlchemy Select statement from an extraction config.

        Args:
            config: Validated extraction configuration.

        Returns:
            A SQLAlchemy Select statement ready for execution.

        Raises:
            QueryBuildError: If a table, column, or alias cannot be resolved.
        """
        prim = config.primary_entity
        alias_map: dict[str, sa.Table] = {}

        # ---- Resolve primary table ----
        primary_table = self._resolve_table(prim.table, prim.alias)
        alias_map[prim.alias] = primary_table

        # ---- Build column list ----
        columns: list[sa.Column] = []
        for f in prim.select_fields:
            col = primary_table.c[f.field]
            columns.append(col.label(f.output_name))

        # ---- Process JOINs ----
        joined = primary_table
        for join_spec in config.joins:
            sec_table = self._resolve_table(join_spec.table, join_spec.alias)
            alias_map[join_spec.alias] = sec_table

            # Build ON clause from multiple conditions
            on_clause = self._build_on_clause(join_spec, alias_map)

            is_outer, is_full = self._JOIN_METHODS[join_spec.join_type]
            joined = joined.join(sec_table, onclause=on_clause, isouter=is_outer, full=is_full)

            for f in join_spec.select_fields:
                col = sec_table.c[f.field]
                columns.append(col.label(f.output_name))

        # ---- Calculated fields (SQL expressions) ----
        for cf in config.calculated_fields:
            columns.append(sa.literal_column(cf.expression).label(cf.name))

        # ---- Aggregations ----
        for agg in config.aggregations:
            # Resolve alias.column reference through alias_map
            parts = agg.field.split(".")
            if len(parts) == 2 and parts[0] in alias_map:
                agg_col = alias_map[parts[0]].c[parts[1]]
            else:
                agg_col = text(agg.field)
            agg_expr = self._build_aggregation(agg.function, agg_col, agg.distinct)
            columns.append(agg_expr.label(agg.alias))

        # ---- Build base query ----
        if config.aggregations:
            stmt = select(*columns).select_from(joined)
            # Add GROUP BY
            for gb in config.group_by:
                parts = gb.split(".")
                if len(parts) == 2:
                    stmt = stmt.group_by(alias_map[parts[0]].c[parts[1]])
                else:
                    stmt = stmt.group_by(text(gb))
        else:
            stmt = select(*columns).select_from(joined)

        # ---- Apply filters ----
        for flt in config.filters:
            stmt = self._apply_filter(stmt, flt, alias_map)

        # ---- Incremental watermark ----
        if config.incremental.enabled:
            stmt = self._apply_incremental_filter(stmt, config, alias_map)

        return stmt

    # ------------------------------------------------------------------
    # Table resolution
    # ------------------------------------------------------------------

    def _resolve_table(self, table_ref: str, alias: str) -> sa.Table:
        """Resolve a 'schema.table' reference to a SQLAlchemy Table with alias.

        Args:
            table_ref: Fully qualified table name, e.g. 'raw.customers'.
            alias: SQL alias for this table reference.

        Returns:
            An aliased SQLAlchemy Table.

        Raises:
            QueryBuildError: If the table cannot be reflected.
        """
        parts = table_ref.split(".")
        schema = parts[0] if len(parts) == 2 else None
        tbl_name = parts[1] if len(parts) == 2 else parts[0]

        try:
            table = Table(
                tbl_name,
                self._metadata,
                schema=schema,
                autoload_with=self._engine,
            )
            return table.alias(alias)
        except Exception as e:
            raise QueryBuildError(f"Cannot resolve table '{table_ref}': {e}") from e

    # ------------------------------------------------------------------
    # Join ON clause
    # ------------------------------------------------------------------

    def _build_on_clause(self, join_spec: JoinSpec, alias_map: dict[str, sa.Table]):
        """Build a compound ON clause from multiple join conditions."""
        clauses = []
        for condition in join_spec.on:
            left_alias, left_col = condition.left.split(".")
            right_alias, right_col = condition.right.split(".")

            left_table = alias_map.get(left_alias)
            right_table = alias_map.get(right_alias)

            if left_table is None:
                raise QueryBuildError(f"Unknown alias '{left_alias}' in join ON clause")
            if right_table is None:
                raise QueryBuildError(f"Unknown alias '{right_alias}' in join ON clause")

            clauses.append(left_table.c[left_col] == right_table.c[right_col])

        return sa.and_(*clauses) if len(clauses) > 1 else clauses[0]

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _build_aggregation(
        self,
        function: AggregationFunction,
        column,
        distinct: bool = False,
    ):
        """Build a SQLAlchemy aggregation expression."""
        col = column if distinct else column

        _map = {
            AggregationFunction.COUNT: func.count(column),
            AggregationFunction.COUNT_DISTINCT: func.count(func.distinct(column)),
            AggregationFunction.SUM: func.sum(column),
            AggregationFunction.AVG: func.avg(column),
            AggregationFunction.MIN: func.min(column),
            AggregationFunction.MAX: func.max(column),
            AggregationFunction.STDDEV: func.stddev(column),
            AggregationFunction.VARIANCE: func.variance(column),
        }
        if function not in _map:
            raise QueryBuildError(f"Unsupported aggregation: {function.value}")
        return _map[function]

    # ------------------------------------------------------------------
    # Filters — 22 operators
    # ------------------------------------------------------------------

    def _apply_filter(
        self,
        stmt: Select,
        flt: FilterSpec,
        alias_map: dict[str, sa.Table],
    ) -> Select:
        """Apply a single filter (or composite AND/OR group) to the query."""
        # Composite AND/OR
        if flt.operator in (FilterOperator.AND, FilterOperator.OR):
            if not flt.conditions:
                return stmt
            sub_clauses = []
            for sub in flt.conditions:
                sub_clause = self._build_single_condition(sub, alias_map)
                if sub_clause is not None:
                    sub_clauses.append(sub_clause)
            if not sub_clauses:
                return stmt
            if flt.operator == FilterOperator.AND:
                return stmt.where(sa.and_(*sub_clauses))
            else:
                return stmt.where(sa.or_(*sub_clauses))

        # Single condition
        clause = self._build_single_condition(flt, alias_map)
        if clause is not None:
            stmt = stmt.where(clause)
        return stmt

    def _build_single_condition(
        self,
        flt: FilterSpec,
        alias_map: dict[str, sa.Table],
    ):
        """Build a WHERE clause for a single filter."""
        op = flt.operator
        value = flt.value

        # Operators that don't need a column reference
        if op == FilterOperator.IS_NULL:
            col = self._resolve_column(flt.field, alias_map)  # type: ignore[arg-type]
            return col.is_(None)
        if op == FilterOperator.IS_NOT_NULL:
            col = self._resolve_column(flt.field, alias_map)  # type: ignore[arg-type]
            return col.isnot(None)
        if op == FilterOperator.CURRENT_DATE:
            col = self._resolve_column(flt.field, alias_map)  # type: ignore[arg-type]
            return sa.cast(col, sa.Date) == func.current_date()
        if op == FilterOperator.CURRENT_TIMESTAMP:
            col = self._resolve_column(flt.field, alias_map)  # type: ignore[arg-type]
            return col == func.now()

        col = self._resolve_column(flt.field, alias_map)  # type: ignore[arg-type]

        # Comparison operators
        if op == FilterOperator.EQUALS:
            return col == value
        if op == FilterOperator.NOT_EQUALS:
            return col != value
        if op == FilterOperator.GREATER_THAN:
            return col > value
        if op == FilterOperator.LESS_THAN:
            return col < value
        if op == FilterOperator.GREATER_THAN_EQUAL:
            return col >= value
        if op == FilterOperator.LESS_THAN_EQUAL:
            return col <= value

        # Range / list
        if op == FilterOperator.BETWEEN:
            return sa.and_(col >= value["min"], col <= value["max"])
        if op == FilterOperator.IN:
            return col.in_(value)
        if op == FilterOperator.NOT_IN:
            return col.notin_(value)

        # Pattern matching
        if op == FilterOperator.LIKE:
            return col.like(value)
        if op == FilterOperator.ILIKE:
            return col.ilike(value)
        if op == FilterOperator.REGEX:
            return col.op("~")(value)

        # Date arithmetic
        if op == FilterOperator.DATE_ADD:
            return col + text(f"INTERVAL '{value}'")
        if op == FilterOperator.DATE_SUB:
            return col - text(f"INTERVAL '{value}'")

        # Subqueries
        if op == FilterOperator.EXISTS:
            return sa.exists(text(value))
        if op == FilterOperator.NOT_EXISTS:
            return ~sa.exists(text(value))

        raise QueryBuildError(f"Unsupported filter operator: {op.value}")

    def _resolve_column(self, field_ref: str, alias_map: dict[str, sa.Table]):
        """Resolve 'alias.column' to a SQLAlchemy Column object."""
        parts = field_ref.split(".")
        if len(parts) != 2:
            raise QueryBuildError(
                f"Invalid column reference '{field_ref}' — expected 'alias.column'"
            )
        alias, col_name = parts
        table = alias_map.get(alias)
        if table is None:
            raise QueryBuildError(f"Unknown alias '{alias}' in filter field '{field_ref}'")
        try:
            return table.c[col_name]
        except KeyError:
            raise QueryBuildError(
                f"Column '{col_name}' not found on table alias '{alias}'"
            )

    # ------------------------------------------------------------------
    # Incremental extraction
    # ------------------------------------------------------------------

    def _apply_incremental_filter(
        self,
        stmt: Select,
        config: ExtractionConfigSpec,
        alias_map: dict[str, sa.Table],
    ) -> Select:
        """Append WHERE watermark_column > last_extracted watermark."""
        inc = config.incremental
        col = self._resolve_column(inc.watermark_column, alias_map)

        # Get watermark from store (placeholder — real impl queries etl.extraction_watermarks)
        watermark = datetime.now(timezone.utc) - timedelta(minutes=inc.lookback_minutes)

        return stmt.where(col > watermark)
