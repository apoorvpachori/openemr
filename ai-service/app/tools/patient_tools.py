"""
Patient data tools — async HTTP calls to the OpenEMR internal PHP proxy.

Security design
───────────────
Tools are created via make_patient_tools(pid, internal_token). The pid and
token live in Python closures — the LLM sees tool functions with no parameters
and cannot change which patient is queried or forge an authentication token.

Each tool returns either:
  {"status": "ok",      "data": [...]}         → real records found
  {"status": "no_data", "message": "..."}       → patient has no records of this type
  {"status": "error",   "message": "..."}       → network/auth failure

The agent (Step 5) maps "no_data" → "No X on file" in the response.
It never infers data from an empty result.
"""

import logging
import os

import httpx
from langchain_core.tools import tool

logger = logging.getLogger("copilot.tools")

# Base URL for the OpenEMR PHP container on the shared Docker network.
# Override with OPENEMR_INTERNAL_URL env var for non-Docker environments.
_OPENEMR_URL = os.getenv("OPENEMR_INTERNAL_URL", "http://openemr:80")
_API_PATH = "/interface/modules/custom_modules/oe-module-clinical-copilot/public/api.php"


async def _fetch(action: str, pid: int, token: str) -> dict:
    """
    Single GET to the internal PHP proxy.

    Uses a fresh httpx.AsyncClient per call — connection pooling would require
    a shared client lifecycle, which adds complexity before Step 7 (observability).
    Each tool call is <5ms on the Docker internal network so the overhead is negligible.
    """
    url = f"{_OPENEMR_URL}{_API_PATH}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params={"action": action, "pid": pid, "token": token})

        if resp.status_code == 401:
            # Token expired or invalid — likely a clock skew or config mismatch.
            logger.error("HMAC auth failed for action=%s pid=%d (HTTP 401)", action, pid)
            return {"status": "error", "message": "Auth token rejected by internal API"}

        if resp.status_code != 200:
            logger.warning("Internal API %s returned HTTP %d", action, resp.status_code)
            return {"status": "error", "message": f"Internal API error (HTTP {resp.status_code})"}

        return resp.json()

    except httpx.TimeoutException:
        logger.error("Timeout calling internal API action=%s pid=%d", action, pid)
        return {"status": "error", "message": f"Timeout fetching {action} — internal API unresponsive"}

    except Exception as exc:
        logger.error("Unexpected error calling internal API action=%s: %s", action, exc)
        return {"status": "error", "message": f"Failed to fetch {action}"}


def make_patient_tools(pid: int, internal_token: str) -> list:
    """
    Return six LangGraph-compatible tool functions with pid and token baked in.

    Why closures: The LLM receives tool descriptions with no parameters. It
    cannot modify pid or the auth token — those values exist only in Python
    memory. This is the correct security pattern for agent tools that access
    sensitive data scoped to a specific user/session.

    Usage:
        tools = make_patient_tools(request.pid, request.internal_token)
        agent = graph.compile(tools=tools)
    """

    @tool
    async def get_demographics() -> dict:
        """Get patient demographics: full name, date of birth, sex, and contact info."""
        return await _fetch("demographics", pid, internal_token)

    @tool
    async def get_medications() -> dict:
        """Get the patient's active medication list including drug name, dosage, and instructions."""
        return await _fetch("medications", pid, internal_token)

    @tool
    async def get_recent_encounters() -> dict:
        """Get the patient's 5 most recent clinical encounters: dates, visit reasons, and encounter types."""
        return await _fetch("encounters", pid, internal_token)

    @tool
    async def get_recent_labs() -> dict:
        """Get the patient's 10 most recent lab results: test name, value, units, reference range, and abnormal flag."""
        return await _fetch("labs", pid, internal_token)

    @tool
    async def get_problems() -> dict:
        """Get the patient's active medical problem list with diagnoses and ICD codes."""
        return await _fetch("problems", pid, internal_token)

    @tool
    async def get_allergies() -> dict:
        """Get the patient's allergy list including allergen, reaction type, and severity."""
        return await _fetch("allergies", pid, internal_token)

    return [
        get_demographics,
        get_medications,
        get_recent_encounters,
        get_recent_labs,
        get_problems,
        get_allergies,
    ]
