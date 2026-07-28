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
    PreAggregationSpec,
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

    # Map join types to SQLAlchemy (isouter, is_full).  RIGHT is handled
    # specially by swapping operands since SQLAlchemy join() only does LEFT.
    _JOIN_METHODS: dict[JoinType, tuple[bool, bool]] = {
        JoinType.INNER: (False, False),
        JoinType.LEFT: (True, False),
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
        self._current_config: ExtractionConfigSpec | None = None  # Set during build()

    def _check_trusted(self, feature: str) -> None:
        """Raise if the current config is untrusted and uses a raw-SQL feature."""
        if self._current_config and not self._current_config.trusted_config:
            raise QueryBuildError(
                f"{feature} requires trusted_config=True. "
                f"Raw SQL expressions are not allowed in untrusted configs."
            )

    def build(
        self,
        config: ExtractionConfigSpec,
        last_watermark: datetime | None = None,
    ) -> Select:
        """Build a SQLAlchemy Select statement from an extraction config.

        Args:
            config: Validated extraction configuration.
            last_watermark: Last successful extraction timestamp.
                If incremental is enabled and this is None (first run),
                falls back to config.incremental.lookback_minutes.

        Returns:
            A SQLAlchemy Select statement ready for execution.

        Raises:
            QueryBuildError: If a table, column, or alias cannot be resolved.
        """
        self._current_config = config
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

        # ---- Build pre-aggregation CTEs ----
        cte_list: list = []
        for pa in config.pre_aggregations:
            cte = self._build_pre_aggregation_cte(pa)
            cte_list.append(cte)
            alias_map[pa.alias] = cte

        # ---- Process JOINs ----
        joined = primary_table
        for join_spec in config.joins:
            # Check if this is a CTE reference or a real table
            if join_spec.alias in alias_map and isinstance(alias_map[join_spec.alias], sa.CTE):
                sec_table = alias_map[join_spec.alias]
            else:
                sec_table = self._resolve_table(join_spec.table, join_spec.alias)
                alias_map[join_spec.alias] = sec_table

            # Build ON clause from multiple conditions
            on_clause = self._build_on_clause(join_spec, alias_map)

            if join_spec.join_type == JoinType.RIGHT:
                # SQLAlchemy join() only does LEFT OUTER.
                # To get RIGHT: swap operands — sec_table LEFT JOIN joined.
                joined = sec_table.join(joined, onclause=on_clause, isouter=True)
            else:
                is_outer, is_full = self._JOIN_METHODS[join_spec.join_type]
                joined = joined.join(sec_table, onclause=on_clause, isouter=is_outer, full=is_full)

            for f in join_spec.select_fields:
                col = sec_table.c[f.field]
                columns.append(col.label(f.output_name))

        # ---- Calculated fields (SQL expressions — trusted config only) ----
        if config.calculated_fields:
            self._check_trusted("calculated_fields")
        for cf in config.calculated_fields:
            columns.append(sa.literal_column(cf.expression).label(cf.name))

        # ---- Aggregations ----
        for agg in config.aggregations:
            # Resolve alias.column reference through alias_map
            parts = agg.field.split(".")
            if len(parts) == 2 and parts[0] in alias_map:
                agg_col = alias_map[parts[0]].c[parts[1]]
            else:
                self._check_trusted(f"aggregation field '{agg.field}'")
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
            # Include the source value in the result so the executor can advance
            # state to the maximum *observed* value after downstream publication.
            watermark_col = self._resolve_column(config.incremental.watermark_column, alias_map)
            columns.append(watermark_col.label("_extraction_watermark"))
            stmt = stmt.with_only_columns(*columns)
            stmt = self._apply_incremental_filter(stmt, config, alias_map, last_watermark)

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
    # Pre-Aggregation CTE
    # ------------------------------------------------------------------

    def _build_pre_aggregation_cte(self, pa: PreAggregationSpec):
        """Build a CTE that pre-aggregates a side table to prevent row multiplication.

        Generates:
            WITH {name} AS (
                SELECT {group_by_cols}, {agg_exprs}
                FROM {from_table}
                WHERE {filters}
                GROUP BY {group_by_cols}
            )
        """
        # Resolve source table
        src_table = self._resolve_table(pa.from_table, pa.alias)

        # Build GROUP BY columns
        group_cols = []
        for gb in pa.group_by:
            parts = gb.split(".")
            if len(parts) == 2 and parts[0] == pa.alias:
                group_cols.append(src_table.c[parts[1]])
            else:
                group_cols.append(text(gb))

        # Build aggregation expressions
        agg_exprs = []
        for agg in pa.aggregations:
            parts = agg.field.split(".")
            if len(parts) == 2 and parts[0] == pa.alias:
                agg_col = src_table.c[parts[1]]
            else:
                agg_col = text(agg.field)
            agg_expr = self._build_aggregation(agg.function, agg_col, agg.distinct)
            agg_exprs.append(agg_expr.label(agg.alias))

        # Build CTE select
        cte_select = select(*group_cols, *agg_exprs)

        # Apply filters within CTE
        pa_alias_map = {pa.alias: src_table}
        for flt in pa.filters:
            cte_select = self._apply_filter(cte_select, flt, pa_alias_map)

        # Apply GROUP BY
        for gb_col in group_cols:
            cte_select = cte_select.group_by(gb_col)

        return cte_select.cte(pa.name)

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

        # Subqueries (trusted config only — raw SQL via text())
        if op == FilterOperator.EXISTS:
            self._check_trusted("EXISTS filter")
            return sa.exists(text(value))
        if op == FilterOperator.NOT_EXISTS:
            self._check_trusted("NOT_EXISTS filter")
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
        last_watermark: datetime | None = None,
    ) -> Select:
        """Append WHERE watermark_column > last_watermark.

        Uses the persisted watermark from a previous successful run.
        On first run (last_watermark is None), falls back to:
            now() - lookback_minutes
        as a safety window.
        """
        inc = config.incremental
        col = self._resolve_column(inc.watermark_column, alias_map)

        if last_watermark is not None:
            watermark = last_watermark
        else:
            # First run — use lookback as a safety window
            watermark = datetime.now(timezone.utc) - timedelta(minutes=inc.lookback_minutes)

        return stmt.where(col > watermark)
