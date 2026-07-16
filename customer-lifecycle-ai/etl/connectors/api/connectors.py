"""
API Connectors - REST and SOAP.

API-based connectors for extracting data from REST APIs and SOAP web services.
Includes authentication, pagination, retry logic, and rate limiting.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import httpx
import pandas as pd

from etl.connectors.factory import register_connector
from etl.connectors.interfaces import ApiConnector
from etl.schemas.connector_schemas import (
    BatchMetadata,
    ConnectorConfig,
    ConnectorInfo,
    Dataset,
    SourceType,
)


# ---------------------------------------------------------------------------
# REST Connector
# ---------------------------------------------------------------------------

@register_connector(
    SourceType.REST,
    ConnectorInfo(
        source_type=SourceType.REST,
        display_name="REST API",
        description="Connector for RESTful APIs with JSON responses",
        supported_operations=["extract", "get_endpoints", "get_schema"],
        version="1.0.0",
        is_implemented=True,
    ),
)
class RestConnector(ApiConnector):
    """REST API connector with pagination, auth, and retry support."""

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self._client: httpx.AsyncClient | None = None
        self._base_url: str = ""

    async def connect(self) -> None:
        """Initialize async HTTP client with auth and timeout."""
        headers: dict[str, str] = {"Accept": "application/json"}

        if self.config.api_key:
            auth_header = self.config.extra_params.get("auth_header", "Authorization")
            auth_prefix = self.config.extra_params.get("auth_prefix", "Bearer")
            headers[auth_header] = f"{auth_prefix} {self.config.api_key}"

        if self.config.username and self.config.password:
            basic_auth = httpx.BasicAuth(
                username=self.config.username,
                password=self.config.password,
            )
        else:
            basic_auth = None

        self._base_url = (self.config.api_base_url or "").rstrip("/")

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            auth=basic_auth,
            timeout=httpx.Timeout(self.config.timeout_seconds),
            limits=httpx.Limits(max_keepalive_connections=5),
        )
        self._connected = True

    async def disconnect(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._connected = False

    async def validate_connection(self) -> bool:
        """Test connectivity by calling the base URL."""
        if self._client is None:
            return False
        try:
            response = await self._client.get("/")
            return response.status_code < 500
        except Exception:
            return False

    async def extract(self) -> AsyncIterator[Dataset]:
        """Extract data from the REST API with pagination support."""
        if not self._connected or self._client is None:
            raise RuntimeError("Cannot extract: connector is not connected.")

        endpoint = self.config.query or self.config.extra_params.get("endpoint", "/")
        pagination_type = self.config.extra_params.get("pagination", "offset")
        max_pages = self.config.extra_params.get("max_pages", 1000)

        batch_id = str(uuid.uuid4())
        all_rows: list[dict[str, Any]] = []
        chunk_index = 0
        page = 1
        offset = 0

        metadata = BatchMetadata(
            batch_id=batch_id,
            source_type=SourceType.REST,
            source_name=self.config.source_name,
            extracted_at=datetime.now(timezone.utc),
            api_endpoint=endpoint,
        )

        # Retry logic
        retries = 0

        while page <= max_pages:
            params: dict[str, Any] = dict(self.config.extra_params.get("query_params", {}))

            if pagination_type == "offset":
                params["offset"] = offset
                params["limit"] = self.config.batch_size
            elif pagination_type == "page":
                params["page"] = page
                params["per_page"] = self.config.batch_size

            try:
                response = await self._client.get(endpoint, params=params)
                response.raise_for_status()
                retries = 0  # Reset on success
            except httpx.HTTPStatusError as e:
                retries += 1
                if retries > self.config.max_retries:
                    raise RuntimeError(
                        f"API request failed after {self.config.max_retries} retries: {e}"
                    ) from e
                await self._disconnect_and_wait(retries)
                continue
            except httpx.RequestError as e:
                retries += 1
                if retries > self.config.max_retries:
                    raise RuntimeError(
                        f"API connection failed after {self.config.max_retries} retries: {e}"
                    ) from e
                await self._disconnect_and_wait(retries)
                continue

            data = response.json()

            # Extract the data array from the response
            data_key = self.config.extra_params.get("data_key", "data")
            if isinstance(data, dict):
                items = data.get(data_key, data.get("results", []))
            elif isinstance(data, list):
                items = data
            else:
                items = []

            if not items:
                break

            all_rows.extend(items if isinstance(items, list) else [items])

            if len(items) < self.config.batch_size:
                break

            page += 1
            offset += self.config.batch_size

        df = pd.DataFrame(all_rows)
        checksum = hashlib.sha256(
            json.dumps(all_rows, sort_keys=True, default=str).encode()
        ).hexdigest()

        metadata.total_rows = len(df)
        metadata.total_chunks = 1
        metadata.checksum_sha256 = checksum
        metadata.extraction_completed_at = datetime.now(timezone.utc)

        yield Dataset(
            data=df,
            metadata=metadata,
            chunk_index=0,
        )

    async def _disconnect_and_wait(self, retry_count: int) -> None:
        """Wait with exponential backoff between retries."""
        import asyncio
        wait = min(2 ** retry_count, 60)  # Cap at 60 seconds
        await asyncio.sleep(wait)

    async def get_endpoints(self) -> list[str]:
        """List available endpoints (returns configured endpoint)."""
        return [self.config.query or self.config.extra_params.get("endpoint", "/")]

    async def get_schema(self, endpoint: str) -> dict[str, Any]:
        """Retrieve OpenAPI schema if available."""
        if self._client is None:
            raise RuntimeError("Not connected.")
        try:
            response = await self._client.get("/openapi.json")
            response.raise_for_status()
            return response.json()
        except Exception:
            return {"error": "Schema not available"}


# ---------------------------------------------------------------------------
# SOAP Connector
# ---------------------------------------------------------------------------

@register_connector(
    SourceType.SOAP,
    ConnectorInfo(
        source_type=SourceType.SOAP,
        display_name="SOAP",
        description="Connector for SOAP/XML web services",
        supported_operations=["extract", "get_endpoints"],
        version="1.0.0",
        is_implemented=True,
    ),
)
class SoapConnector(ApiConnector):
    """SOAP web service connector using httpx with XML payloads."""

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        self._client: httpx.AsyncClient | None = None
        self._wsdl_url: str = ""

    async def connect(self) -> None:
        """Initialize HTTP client for SOAP communication."""
        headers: dict[str, str] = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": self.config.extra_params.get("soap_action", ""),
        }

        auth: httpx.BasicAuth | None = None
        if self.config.username and self.config.password:
            auth = httpx.BasicAuth(
                username=self.config.username,
                password=self.config.password,
            )

        self._wsdl_url = (self.config.api_base_url or "").rstrip("/")

        self._client = httpx.AsyncClient(
            base_url=self._wsdl_url,
            headers=headers,
            auth=auth,
            timeout=httpx.Timeout(self.config.timeout_seconds),
        )
        self._connected = True

    async def disconnect(self) -> None:
        """Close HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._connected = False

    async def validate_connection(self) -> bool:
        """Test connectivity to SOAP endpoint."""
        if self._client is None:
            return False
        try:
            response = await self._client.get("/")
            return response.status_code < 500
        except Exception:
            return False

    async def extract(self) -> AsyncIterator[Dataset]:
        """Extract data from SOAP web service."""
        if not self._connected or self._client is None:
            raise RuntimeError("Cannot extract: connector is not connected.")

        soap_body = self.config.extra_params.get("soap_body", "")
        if not soap_body:
            raise ValueError("SOAP body XML must be provided in extra_params.soap_body")

        batch_id = str(uuid.uuid4())

        try:
            response = await self._client.post("/", content=soap_body)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise RuntimeError(f"SOAP request failed: {e}") from e

        # Parse XML response into DataFrame
        df = pd.read_xml(response.text)

        metadata = BatchMetadata(
            batch_id=batch_id,
            source_type=SourceType.SOAP,
            source_name=self.config.source_name,
            extracted_at=datetime.now(timezone.utc),
            extracted_completed_at=datetime.now(timezone.utc),
            total_rows=len(df),
            total_chunks=1,
            checksum_sha256=hashlib.sha256(response.text.encode()).hexdigest(),
            api_endpoint=self._wsdl_url,
        )

        yield Dataset(
            data=df,
            metadata=metadata,
            chunk_index=0,
        )

    async def get_endpoints(self) -> list[str]:
        """Return the configured SOAP endpoint."""
        return [self._wsdl_url]

    async def get_schema(self, endpoint: str) -> dict[str, Any]:
        """SOAP schema retrieval (WSDL)."""
        if self._client is None:
            raise RuntimeError("Not connected.")
        try:
            response = await self._client.get("/?wsdl")
            return {"wsdl": response.text[:10000]}
        except Exception:
            return {"error": "WSDL not available"}
