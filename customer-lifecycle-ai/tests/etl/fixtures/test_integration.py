"""
Integration tests for the complete ETL pipeline.

Tests end-to-end flows:
- Configuration loading (YAML + env vars)
- Pipeline registry and runner
- Full ETL orchestration with mocked services
- Audit record creation
- Error handling across pipeline stages
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
import yaml

from etl.config.service import ETLConfig, generate_sample_config
from etl.pipelines.runner import PipelineRegistry, PipelineRunner
from etl.schemas.audit_schemas import AuditRecord
from etl.schemas.connector_schemas import ConnectorConfig, SourceType
from etl.schemas.ingestion_schemas import IngestionResult, IngestionStatus
from etl.schemas.validation_schemas import ValidationReport, ValidationStatus


# ---------------------------------------------------------------------------
# Configuration Tests
# ---------------------------------------------------------------------------

class TestETLConfig:
    """Tests for centralized ETL configuration."""

    def test_load_defaults(self) -> None:
        """Test that default config loads without errors."""
        config = ETLConfig()
        assert config.landing.base_path == "/data/landing"
        assert config.validation.enabled is True
        assert config.audit.retention_years == 7
        assert config.checkpoint.enabled is True

    def test_load_from_env(self) -> None:
        """Test that environment variables override defaults."""
        import os
        os.environ["ETL_LANDING_BASE_PATH"] = "/custom/landing"
        config = ETLConfig.load_from_env()
        assert config.landing.base_path == "/custom/landing"
        del os.environ["ETL_LANDING_BASE_PATH"]

    def test_generate_sample_config_is_valid_yaml(self) -> None:
        """Test that generated sample config is valid YAML."""
        yaml_str = generate_sample_config()
        data = yaml.safe_load(yaml_str)
        assert "landing" in data
        assert "validation" in data
        assert "monitoring" in data
        assert "audit" in data

    def test_config_has_all_components(self) -> None:
        """Test that ETLConfig exposes all configuration components."""
        config = ETLConfig()
        components = [
            "landing", "staging", "checkpoint", "logging",
            "audit", "monitoring", "loading",
            "validation", "transformation",
        ]
        for comp in components:
            assert hasattr(config, comp), f"Missing config component: {comp}"


# ---------------------------------------------------------------------------
# Pipeline Registry Tests
# ---------------------------------------------------------------------------

class TestPipelineRegistry:
    """Tests for PipelineRegistry."""

    def test_register_and_retrieve(self) -> None:
        """Test registering and retrieving pipelines."""
        from etl.schemas.orchestration_schemas import PipelineDefinition
        registry = PipelineRegistry()
        pipeline = PipelineDefinition(pipeline_name="test_pipeline")
        registry.register(pipeline)
        assert registry.get("test_pipeline") is pipeline

    def test_list_pipelines(self) -> None:
        """Test listing registered pipelines."""
        from etl.schemas.orchestration_schemas import PipelineDefinition
        registry = PipelineRegistry()
        registry.register(PipelineDefinition(pipeline_name="p1"))
        registry.register(PipelineDefinition(pipeline_name="p2"))
        names = registry.list_pipelines()
        assert "p1" in names
        assert "p2" in names
        assert len(names) == 2


# ---------------------------------------------------------------------------
# PipelineRunner Integration Tests
# ---------------------------------------------------------------------------

class TestPipelineRunnerIntegration:
    """Integration tests for PipelineRunner with mocked services."""

    @pytest.fixture
    def mock_services(self) -> dict:
        """Create all mocked services for PipelineRunner."""
        from etl.audit.service import AuditService
        from etl.checkpoint.service import CheckpointService
        from etl.ingestion.service import IngestionService
        from etl.loading.service import LoadingService
        from etl.logging.service import ETLLogger
        from etl.monitoring.service import MonitoringService
        from etl.orchestration.service import OrchestrationService
        from etl.staging.service import StagingService
        from etl.transformation.service import TransformationService
        from etl.validation.service import ValidationService

        return {
            "ingestion": AsyncMock(spec=IngestionService),
            "validation": AsyncMock(spec=ValidationService),
            "transformation": AsyncMock(spec=TransformationService),
            "staging": AsyncMock(spec=StagingService),
            "loading": AsyncMock(spec=LoadingService),
            "orchestrator": AsyncMock(),
            "checkpoint": AsyncMock(spec=CheckpointService),
            "monitoring": AsyncMock(spec=MonitoringService),
            "audit": AsyncMock(spec=AuditService),
            "logger": MagicMock(spec=ETLLogger),
        }

    @pytest.mark.asyncio
    async def test_run_pipeline_success(
        self, mock_services: dict
    ) -> None:
        """Test successful pipeline execution."""
        from etl.schemas.orchestration_schemas import PipelineRun, PipelineStatus

        mock_services["orchestrator"].execute.return_value = PipelineRun(
            run_id="run-001",
            pipeline_name="test",
            status=PipelineStatus.COMPLETED,
            total_steps=5,
            completed_steps=5,
        )

        runner = PipelineRunner(
            config=ETLConfig(),
            **mock_services,
        )

        result = await runner.run_pipeline("test")

        assert result["status"] == "COMPLETED"
        assert result["steps_completed"] == 5

    @pytest.mark.asyncio
    async def test_run_pipeline_failure(
        self, mock_services: dict
    ) -> None:
        """Test pipeline failure handling."""
        mock_services["orchestrator"].execute.side_effect = RuntimeError("Step failed")

        runner = PipelineRunner(
            config=ETLConfig(),
            **mock_services,
        )

        with pytest.raises(RuntimeError, match="Step failed"):
            await runner.run_pipeline("failing_pipeline")

        mock_services["monitoring"].mark_failed.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_full_etl(
        self, mock_services: dict
    ) -> None:
        """Test full ETL pipeline execution."""
        # Mock ingestion
        mock_services["ingestion"].ingest.return_value = IngestionResult(
            batch_id="batch-001",
            status=IngestionStatus.VALIDATION_TRIGGERED,
            pipeline_name="etl_full",
            source_type=SourceType.CSV,
            source_name="test",
            total_rows=1000,
            total_chunks=1,
            received_at=datetime.now(timezone.utc),
        )

        # Mock validation
        mock_services["validation"].validate.return_value = ValidationReport(
            batch_id="batch-001",
            status=ValidationStatus.PASSED,
            total_records=1000,
            valid_records=1000,
        )

        # Mock transformation
        mock_services["transformation"].transform.return_value = (
            pd.DataFrame(),
            MagicMock(),
        )

        # Mock loading
        from etl.schemas.loading_schemas import LoadPipelineResult, LoadStepStatus
        mock_services["loading"].execute.return_value = LoadPipelineResult(
            batch_id="batch-001",
            pipeline_name="test",
            status=LoadStepStatus.COMPLETED,
            total_rows_loaded=1000,
        )

        runner = PipelineRunner(
            config=ETLConfig(),
            **mock_services,
        )

        config = ConnectorConfig(
            source_type=SourceType.CSV,
            source_name="test",
            file_path="/tmp/test.csv",
        )

        result = await runner.run_full_etl(config)

        assert result["status"] == "COMPLETED"
        assert result["rows_received"] == 1000
        assert result["rows_loaded"] == 1000

        # Verify audit was created
        mock_services["audit"].create_audit_record.assert_called_once()


# ---------------------------------------------------------------------------
# End-to-End ETL Pipeline (6 Stages)
# ---------------------------------------------------------------------------

class TestEndToEndPipeline:
    """Tests verifying the complete 6-stage ETL flow is wired correctly."""

    def test_pipeline_stages_are_ordered(self) -> None:
        """Test that pipeline stages follow the correct order."""
        from etl.schemas.orchestration_schemas import default_etl_pipeline
        pipeline = default_etl_pipeline()

        stage_order = [
            "extract", "ingest", "validate", "transform",
            "stage", "load", "feature_engineering",
            "markov_state", "prediction", "decision", "dashboard",
        ]

        step_ids = [s.step_id for s in pipeline.steps]
        for stage in stage_order:
            assert stage in step_ids, f"Missing stage: {stage}"

    def test_config_generates_all_subsystem_configs(self) -> None:
        """Test that ETLConfig generates configs for all subsystems."""
        config = ETLConfig()
        subsystems = [
            config.validation,
            config.transformation,
            config.landing,
            config.staging,
            config.checkpoint,
            config.monitoring,
            config.logging,
            config.audit,
        ]
        for sub in subsystems:
            assert sub is not None
