"""
Pydantic models defining the contract between the PHP bridge and the AI service.

These models do two things:
1. Validate incoming data automatically (FastAPI returns 422 if shape is wrong)
2. Document the expected structure explicitly — no guessing what PHP sends

PHP sends: pid, auth_user, message, internal_token.
Python fetches all patient data itself via the HMAC-authenticated api.php proxy.
"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """
    Payload sent by ChatController.php after all security validation passes.

    pid and auth_user come from the PHP session — not from the browser.
    PHP is the authority on identity; Python trusts what PHP sends here.

    internal_token is a short-lived HMAC token (30s TTL) that allows Python
    tools to call back to api.php and fetch patient data. It is signed over
    "{pid}:{timestamp}" so it cannot be replayed for a different patient.
    """
    pid: int
    auth_user: str
    message: str
    internal_token: str


class Citation(BaseModel):
    """A traceable source for a single claim in the response."""
    type: str             # "medication" | "lab" | "encounter" | "problem" | "allergy"
    title: str            # human-readable label, e.g. "Metformin 1000mg BID"
    index: int | None = None   # position in the source list for precise traceability


class ChatResponse(BaseModel):
    """
    Standard response shape returned to the PHP bridge, which forwards it to the
    browser unchanged.

    verification_status drives UI rendering:
      "pass"    → normal response
      "partial" → response shown with a yellow warning (some claims unverified)
      "fail"    → error state shown (response blocked by verification node)
    """
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    verification_status: str = "pass"
    warnings: list[str] = Field(default_factory=list)
