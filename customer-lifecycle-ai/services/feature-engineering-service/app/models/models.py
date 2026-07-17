"""Feature Engineering — SQLAlchemy 2.0 ORM for customer_features."""
from __future__ import annotations
from datetime import date, datetime
from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from shared.database.base import Base


class CustomerFeatures(Base):
    __tablename__ = "customer_features"
    __table_args__ = (
        UniqueConstraint("customer_id", "as_of_date", name="uq_customer_as_of"),
        {"comment": "Point-in-time customer feature snapshots for ML training"},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    days_since_last_txn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    days_since_first_txn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    txn_count_30d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    txn_count_90d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    txn_count_180d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_days_between_txn: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    total_amount_90d: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    avg_amount_90d: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    total_amount_180d: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    amount_growth_ratio: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    distinct_channels_90d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distinct_txn_types_90d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dominant_channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    amount_stddev_90d: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
