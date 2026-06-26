# node/tests/test_compose_healthcheck.py
"""Guard: both running node compose files declare a healthcheck for the
marznode service."""
import re
from pathlib import Path

NODE_DIR = Path(__file__).resolve().parents[1]


def _has_healthcheck(name: str) -> bool:
    return "healthcheck:" in (NODE_DIR / name).read_text()


def test_compose_files_have_healthcheck():
    for name in ("compose.yml", "compose.preprod.yml"):
        assert _has_healthcheck(name), f"{name} missing healthcheck"
