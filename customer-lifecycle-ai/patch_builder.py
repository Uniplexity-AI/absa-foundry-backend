import sys
with open('etl/extraction/query_builder.py', 'r', encoding='utf-8') as f:
    code = f.read()

target = '''    def _build_aggregation(
        self,
        function: AggregationFunction,
        column,
        distinct: bool = False,
    ):
        \"\"\"Build a SQLAlchemy aggregation expression.\"\"\"
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
        return _map[function]'''

replacement = '''    def _build_aggregation(
        self,
        function: AggregationFunction,
        column,
        distinct: bool = False,
        filter_expr = None
    ):
        \"\"\"Build a SQLAlchemy aggregation expression.\"\"\"
        from sqlalchemy import text
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
            AggregationFunction.COUNT_FILTER: func.count(column).filter(filter_expr) if filter_expr is not None else func.count(column),
            AggregationFunction.COUNT_DISTINCT_FILTER: func.count(func.distinct(column)).filter(filter_expr) if filter_expr is not None else func.count(func.distinct(column)),
            AggregationFunction.SUM_FILTER: func.sum(column).filter(filter_expr) if filter_expr is not None else func.sum(column),
            AggregationFunction.AVG_FILTER: func.avg(column).filter(filter_expr) if filter_expr is not None else func.avg(column),
            AggregationFunction.MIN_FILTER: func.min(column).filter(filter_expr) if filter_expr is not None else func.min(column),
            AggregationFunction.MAX_FILTER: func.max(column).filter(filter_expr) if filter_expr is not None else func.max(column),
        }
        if function not in _map:
            raise QueryBuildError(f"Unsupported aggregation: {function.value}")
        return _map[function]'''

if 'filter_expr = None' not in code:
    code = code.replace(target, replacement)
    
    # Also patch _apply_aggregations to pass filter_expr
    target2 = '''agg_col = self._build_aggregation(agg.function, col, distinct=agg.distinct).label(agg.alias)'''
    replacement2 = '''agg_col = self._build_aggregation(agg.function, col, distinct=agg.distinct, filter_expr=sa.text(agg.filter) if agg.filter else None).label(agg.alias)'''
    code = code.replace(target2, replacement2)

    with open('etl/extraction/query_builder.py', 'w', encoding='utf-8') as f:
        f.write(code)
