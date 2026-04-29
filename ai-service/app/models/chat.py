"""
Pydantic models defining the contract between the PHP bridge and the AI service.

These models do two things:
1. Validate incoming data automatically (FastAPI returns 422 if shape is wrong)
2. Document the expected structure explicitly — no guessing what PHP sends

When Step 4 (PatientContextService.php) is built, the context fields here
must match exactly what PHP packs into the JSON payload.
"""

from pydantic import BaseModel, Field


class PatientContext(BaseModel):
    """
    Structured patient data fetched by PHP from OpenEMR's DB before the request
    reaches Python. All fields are optional — any can be absent for a new patient,
    incomplete import, or a patient with no history in that category.

    The agent (Step 5) must handle empty lists and None gracefully — never assume
    data exists.
    """
    patient: dict | None = None
    encounters: list[dict] = Field(default_factory=list)
    medications: list[dict] = Field(default_factory=list)
    problems: list[dict] = Field(default_factory=list)
    allergies: list[dict] = Field(default_factory=list)
    labs: list[dict] = Field(default_factory=list)


class ChatRequest(BaseModel):
    """
    Payload sent by ChatController.php after all security validation passes.

    pid and auth_user come from the PHP session — not from the browser.
    PHP is the authority on identity; Python trusts what PHP sends here.
    """
    pid: int
    auth_user: str
    message: str
    context: PatientContext = Field(default_factory=PatientContext)


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
