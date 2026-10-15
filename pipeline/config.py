"""Config loading. Tunables come from config.yaml, the measured quarter from env.

Freeze and hash logic are not here yet.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).with_name("config.yaml")
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Return config.yaml parsed as a dict. Nothing is added or changed."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _env_file_value(key: str, env_path: Path = ENV_PATH) -> str | None:
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    return None


def measured_period_end(env_path: Path = ENV_PATH) -> date:
    """MEASURED_PERIOD_END from the environment, falling back to .env. ISO date, required."""
    raw = os.environ.get("MEASURED_PERIOD_END") or _env_file_value("MEASURED_PERIOD_END", env_path)
    if not raw or not raw.strip():
        raise RuntimeError("MEASURED_PERIOD_END is not set. Put an ISO date such as 2026-06-30 in .env.")
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as e:
        raise RuntimeError(f"MEASURED_PERIOD_END must be an ISO date (YYYY-MM-DD), got {raw!r}") from e


def load_env_file(env_path: Path = ENV_PATH) -> None:
    """Load KEY=VALUE lines from .env into os.environ without overriding variables already set."""
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
