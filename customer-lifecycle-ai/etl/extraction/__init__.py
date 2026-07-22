"""
ETL Extraction Module — Dynamic Extractor, Unifier & Validation Engine.

Pre-processor that sits before the ETL engine. Reads YAML extraction specs
to dynamically build SQL queries, validate structural integrity, and route
failures to a Dead-Letter Queue.

Architecture:
    YAML Spec → Version Guard → Join Validator → Query Builder
    → Streaming Extraction → Pydantic v2 Validation → Business Rules
    → DLQ (failures) / ETL Engine (valid records)

Full spec: docs/architecture/etl/dynamic-extractor-spec.md
"""
