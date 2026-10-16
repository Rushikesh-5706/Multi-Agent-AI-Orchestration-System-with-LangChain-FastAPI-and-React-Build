from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_all_up_returns_200() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("redis.asyncio.from_url") as mock_redis_from_url:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.aclose = AsyncMock()
            mock_redis_from_url.return_value = mock_client

            resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["database"] == "up"
            assert data["redis"] == "up"


@pytest.mark.asyncio
async def test_health_redis_down_returns_503() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("redis.asyncio.from_url") as mock_redis_from_url:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(side_effect=ConnectionError("Connection refused"))
            mock_client.aclose = AsyncMock()
            mock_redis_from_url.return_value = mock_client

            resp = await client.get("/health")
            assert resp.status_code == 503
            data = resp.json()
            assert data["status"] == "degraded"
            assert data["database"] == "up"
            assert data["redis"] == "down"


@pytest.mark.asyncio
async def test_api_health_alias_works_and_absent_from_openapi() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("redis.asyncio.from_url") as mock_redis_from_url:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.aclose = AsyncMock()
            mock_redis_from_url.return_value = mock_client

            resp = await client.get("/api/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"

    # OpenAPI schema verification
    openapi_schema = app.openapi()
    assert "/health" in openapi_schema["paths"]
    assert "/api/health" not in openapi_schema["paths"]
