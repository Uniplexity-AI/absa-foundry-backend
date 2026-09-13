"""Pydantic schemas for Model Management Service."""
from pydantic import BaseModel, ConfigDict, Field
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import UUID

class CalibrationProposalRequest(BaseModel):
    model_id: UUID
    proposed_threshold: float = Field(..., ge=0.0, le=1.0)
    metrics_snapshot: Dict[str, Any]

class CalibrationProposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    model_id: UUID
    proposed_threshold: float
    metrics_snapshot: Dict[str, Any]
    status: str
    created_at: datetime
    created_by: Optional[str] = None

class FeatureSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    feature_name: str
    display_name: str
    data_type: str
    category: str
    missing_rate: float
    importance_score: float
    allowed_for_training: bool

class RetrainRequest(BaseModel):
    feature_ids: List[UUID]
    dataset_version: str

class RetrainResponse(BaseModel):
    job_id: str
    status: str

class ModelMetrics(BaseModel):
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    auc_roc: float
    confusion_matrix: Dict[str, int]

class ModelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    model_family: str
    model_version: str
    status: str
    optimal_threshold: Optional[float] = None
    evaluation_metrics: Optional[Dict[str, Any]] = None
    created_at: datetime
    created_by: Optional[str] = None

class ModelComparisonResponse(BaseModel):
    champion: Optional[ModelResponse] = None
    challenger: Optional[ModelResponse] = None

class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    timestamp: datetime
    user_id: str
    action: str
    model_id: Optional[UUID] = None
    reason: Optional[str] = None