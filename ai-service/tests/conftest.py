"""
Shared pytest fixtures for all test modules.

Fixtures here are available to every test file without importing — pytest
discovers them automatically from conftest.py.
"""

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def patient_phil() -> dict:
    """Real schema-verified data for pid=1 (Phil Belford) from the demo DB."""
    return json.loads((FIXTURES_DIR / "patients.json").read_text())["pid_1"]


@pytest.fixture
def patient_susan() -> dict:
    """Real schema-verified data for pid=2 (Susan Underwood) from the demo DB."""
    return json.loads((FIXTURES_DIR / "patients.json").read_text())["pid_2"]


# ── Tool response fixtures ────────────────────────────────────────────────────
# These mirror exactly what api.php returns, keyed by the `action` param.

@pytest.fixture
def medications_ok() -> dict:
    return {
        "status": "ok",
        "data": [
            {"title": "Norvasc", "drug_dosage_instructions": None},
            {"title": "Lisinopril", "drug_dosage_instructions": None},
        ],
    }


@pytest.fixture
def problems_ok() -> dict:
    return {
        "status": "ok",
        "data": [
            {"title": "HTN", "diagnosis": "ICD9:401.0"},
            {"title": "Chronic Renal Insufficiency", "diagnosis": "ICD9:585.1"},
        ],
    }


@pytest.fixture
def allergies_ok() -> dict:
    return {
        "status": "ok",
        "data": [{"title": "penicillin", "reaction": ""}],
    }


@pytest.fixture
def no_data() -> dict:
    return {"status": "no_data", "message": "No records found for this patient"}


@pytest.fixture
def error_response() -> dict:
    return {"status": "error", "message": "Auth token rejected by internal API"}
