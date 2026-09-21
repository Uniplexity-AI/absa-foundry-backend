"""One definition of "this customer is hidden" for every customer-facing read.

Deleting a customer is a **soft** delete: ``public.customers_clean.is_deleted``
is flagged and every customer-facing read filters it out — see
``gateway/services/customer_admin_service.py`` for the write side and
``database/migrations/016_customer_soft_delete.sql`` for why the rows stay.

The rule must not drift between queries, so it lives here as one composable SQL
fragment instead of being re-typed into every statement. A read that forgets it
silently counts deleted customers — which is exactly the bug that made
``/states/count`` say 4999 while ``/states/lifecycle-stages`` still said 5000.

The fragment is a ``NOT EXISTS`` subquery rather than a join predicate so it can
be appended to any statement that can name the customer id, whether or not that
statement already joins ``customers_clean``. The subquery uses its own alias
(``sd``) so it can never collide with an outer ``customers_clean`` join aliased
``cc``.
"""
from __future__ import annotations

import re

#: Only a bare or schema-qualified identifier is accepted. The fragment is
#: interpolated into statement text (parameters cannot name a column), so this
#: is the guard that keeps the call sites injection-free.
_CUSTOMER_ID_EXPR = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?")

_SUBQUERY_ALIAS = "sd"


def live_customer_filter(customer_id_expr: str) -> str:
    """Return a SQL fragment that excludes soft-deleted customers.

    Args:
        customer_id_expr: the column holding the customer id, optionally
            qualified with its table, e.g. ``"customer_states.customer_id"`` or
            ``"cs.customer_id"``.

    Returns:
        A single-line ``AND NOT EXISTS (...)`` predicate, meant to be appended
        to the ``WHERE`` clause of the statement being built.

    Raises:
        ValueError: if ``customer_id_expr`` is not a plain identifier.
    """
    if not _CUSTOMER_ID_EXPR.fullmatch(customer_id_expr):
        raise ValueError(
            f"customer_id_expr must be a bare or qualified SQL identifier, got {customer_id_expr!r}"
        )
    return (
        f"AND NOT EXISTS (SELECT 1 FROM public.customers_clean {_SUBQUERY_ALIAS} "
        f"WHERE {_SUBQUERY_ALIAS}.customer_id = {customer_id_expr} "
        f"AND {_SUBQUERY_ALIAS}.is_deleted)"
    )
