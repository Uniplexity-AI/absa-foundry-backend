from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, func, Numeric, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from shared.database.base import Base

class NextOfKin(Base):
    __tablename__ = "next_of_kin"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relationship: Mapped[str] = mapped_column(String(100), nullable=True)
    phone_number: Mapped[str] = mapped_column(String(50), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class EngagementCase(Base):
    __tablename__ = "engagement_cases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    case_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="OPEN")
    assigned_agent_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    interactions: Mapped[List["EngagementInteraction"]] = relationship("EngagementInteraction", back_populates="case")
    promises: Mapped[List["Promise"]] = relationship("Promise", back_populates="case")

class EngagementInteraction(Base):
    __tablename__ = "engagement_interactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(Integer, ForeignKey("engagement_cases.id"), nullable=False)
    interaction_channel: Mapped[str] = mapped_column(String(50), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cross_sell_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dormancy_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    recommendation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    customer_experience: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    branch_to_visit: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    customer_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    interaction_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    case: Mapped["EngagementCase"] = relationship("EngagementCase", back_populates="interactions")

class Promise(Base):
    __tablename__ = "promises"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(Integer, ForeignKey("engagement_cases.id"), nullable=False)
    promise_type: Mapped[str] = mapped_column(String(50), nullable=False)
    promise_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    amount: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    is_fulfilled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    case: Mapped["EngagementCase"] = relationship("EngagementCase", back_populates="promises")
