"""
pytest 共享 fixtures
"""
from __future__ import annotations

import pytest
from pathlib import Path

# 测试夹具目录
FIXTURES_DIR = Path(__file__).parent / "fixtures"
KOTLIN_FIXTURE = FIXTURES_DIR / "kotlin" / "sample_class.kt"
JAVA_FIXTURE = FIXTURES_DIR / "java" / "sample_class.java"


@pytest.fixture
def kotlin_fixture_path() -> Path:
    return KOTLIN_FIXTURE


@pytest.fixture
def java_fixture_path() -> Path:
    return JAVA_FIXTURE


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR
