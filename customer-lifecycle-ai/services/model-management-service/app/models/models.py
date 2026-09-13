"""
Model Management Service - SQLAlchemy ORM Models
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB, BOOLEAN, TEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship
from shared.database.base import Base, TimestampMixin, AuditMixin, SoftDeleteMixin

class ModelRegistry(Base, AuditMixin, SoftDeleteMixin):
    __tablename__ = "model_registry"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_family: Mapped[str] = mapped_column(String(255))
    model_version: Mapped[str] = mapped_column(String(50))
    algorithm: Mapped[str] = mapped_column(String(100))
    training_dataset_version: Mapped[str] = mapped_column(String(100))
    feature_set_version: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50)) # ENUM: TRAINING, TRAINED, VALIDATING, VALIDATED, CHALLENGER, APPROVED, CHAMPION, RETIRED
    optimal_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    hyperparameters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    evaluation_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class FeatureRegistry(Base, AuditMixin, SoftDeleteMixin):
    __tablename__ = "feature_registry"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feature_name: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(255))
    data_type: Mapped[str] = mapped_column(String(50))
    category: Mapped[str] = mapped_column(String(100))
    missing_rate: Mapped[float] = mapped_column(Float, default=0.0)
    importance_score: Mapped[float] = mapped_column(Float, default=0.0)
    allowed_for_training: Mapped[bool] = mapped_column(BOOLEAN, default=True)
    allowed_for_simulation: Mapped[bool] = mapped_column(BOOLEAN, default=True)

class CalibrationProposal(Base, AuditMixin, SoftDeleteMixin):
    __tablename__ = "calibration_proposals"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("model_registry.id"))
    proposed_threshold: Mapped[float] = mapped_column(Float)
    metrics_snapshot: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(50)) # PENDING, APPROVED, REJECTED
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    user_id: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(255))
    model_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("model_registry.id"), nullable=True)
    previous_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(TEXT, nullable=True)