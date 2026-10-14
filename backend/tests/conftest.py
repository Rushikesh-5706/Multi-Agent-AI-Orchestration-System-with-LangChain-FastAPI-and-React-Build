from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("LLM_API_KEY", "test-key-groq")
os.environ.setdefault("OPENWEATHER_API_KEY", "test-key-weather")
os.environ.setdefault("TOOL_SIMULATED_DELAY_SECONDS", "0")
