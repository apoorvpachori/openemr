"""
Verification layer — checks every claim in the agent's answer against the
raw data the tools actually returned.

Why a second LLM call instead of string matching:
  String matching fails on paraphrasing. "kidney disease" won't match
  "Chronic Renal Insufficiency" even though they refer to the same thing.
  The LLM understands clinical synonyms and can judge whether a claim is
  genuinely supported by the source data.

Structured output (Pydantic) means the result is always machine-readable —
no regex parsing of free-text, no risk of the verifier's response being
misinterpreted.
"""

import json
from typing import Literal

from langchain_openai import ChatOpenAI
from pydantic import BaseModel


class VerificationResult(BaseModel):
    """Structured output from the verification LLM call."""

    # pass    → all claims are supported — return answer as-is
    # partial → some claims are unsupported — sanitize node flags them
    # fail    → answer is fundamentally unreliable — fallback node replaces it
    status: Literal["pass", "partial", "fail"]
    unsupported_claims: list[str] = []
    reasoning: str = ""


_VERIFY_PROMPT = """\
You are a clinical data verifier. Your only job is to check whether every \
claim in the generated answer is directly supported by the raw source data below.

A claim is UNSUPPORTED if:
- It states a specific value (dosage, lab result, date) that differs from \
or does not appear in the source data
- It mentions a condition, medication, or finding not present in the source data
- It makes an inference beyond what the data explicitly states \
(e.g. "Stage 3 CKD" when the record only says "Chronic Renal Insufficiency")

Be strict. If it is not explicitly in the data, it is unsupported.

--- SOURCE DATA ---
{tool_results}

--- GENERATED ANSWER ---
{answer}
"""


async def verify_response(answer: str, tool_results: dict) -> VerificationResult:
    """
    Run a structured LLM call to verify every claim in the answer.

    Returns a VerificationResult with:
      - status: pass / partial / fail
      - unsupported_claims: list of specific phrases that couldn't be verified
      - reasoning: brief explanation (useful in LangSmith traces)
    """
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    structured_llm = llm.with_structured_output(VerificationResult)

    prompt = _VERIFY_PROMPT.format(
        tool_results=json.dumps(tool_results, indent=2, default=str),
        answer=answer,
    )

    return await structured_llm.ainvoke(prompt)
