#!/usr/bin/env python3
"""
LangSmith behavioral evaluation suite for the Clinical Co-Pilot.

How it works
------------
1. Loads ground-truth cases from a dataset JSON file.
   Each case has a question, the patient's pid, and a list of keywords
   that MUST appear in a correct answer.

2. Runs the live AI service (/chat endpoint) for each case.
   Real LLM + real DB via HMAC — this is an end-to-end test.

3. An LLM judge (GPT-4o, temp=0) scores each answer 0.0 / 0.5 / 1.0:
     1.0 = all required keywords present (exact or clinical synonym)
     0.5 = some keywords present, some missing
     0.0 = no keywords present OR answer contains fabricated facts

4. Creates a named dataset in LangSmith and logs each case as a run
   with score feedback. The experiment appears in your LangSmith dashboard
   under Project: clinical-copilot.

5. Prints a pass/fail report. Exits with code 1 if pass rate < 80%.

Prerequisites
-------------
  - AI service running at AI_SERVICE_URL (default: http://localhost:8001)
  - OpenEMR running with demo data (pid=1 and pid=2 populated)
  - Env vars: OPENAI_API_KEY, LANGSMITH_API_KEY, COPILOT_HMAC_SECRET

Usage
-----
  # From ai-service/ directory:
  python tests/evals/run_evals.py

  # Against deployed service:
  AI_SERVICE_URL=http://104.248.217.251:8001 python tests/evals/run_evals.py


Datasets
--------
  dataset.json         — factual retrieval (basic correctness)
  dataset_persona.json — Dr. Sarah Chen's real workflow questions (USERS.md)

Usage
-----
  # Basic factual evals (default):
  python tests/evals/run_evals.py

  # Persona-grounded evals (USERS.md use cases):
  python tests/evals/run_evals.py --dataset dataset_persona.json

  # Against deployed service:
  AI_SERVICE_URL=http://104.248.217.251:8001 python tests/evals/run_evals.py
"""

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from langchain_openai import ChatOpenAI
from langsmith import Client

# ── Configuration ─────────────────────────────────────────────────────────────

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8001")
HMAC_SECRET = os.getenv("COPILOT_HMAC_SECRET", "dev-hmac-secret")
LANGSMITH_PROJECT = os.getenv("LANGCHAIN_PROJECT", "clinical-copilot")
PASS_THRESHOLD = 0.8   # 80% of cases must score >= 0.5 to pass

EVALS_DIR = Path(__file__).parent

# Dataset name in LangSmith is derived from the file name at runtime.
# dataset.json         → "clinical-copilot-ground-truth"
# dataset_persona.json → "clinical-copilot-persona"


# ── Token generation ──────────────────────────────────────────────────────────

def make_token(pid: int) -> str:
    """Generate a fresh HMAC token for the given pid (same logic as PHP side)."""
    ts = int(time.time())
    sig = hmac.new(
        HMAC_SECRET.encode(),
        f"{pid}:{ts}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{ts}:{sig}"


# ── Agent call ────────────────────────────────────────────────────────────────

async def call_agent(pid: int, question: str) -> dict:
    """Call the live /chat endpoint and return the full response dict."""
    token = make_token(pid)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{AI_SERVICE_URL}/chat",
            json={
                "pid": pid,
                "auth_user": "eval-runner",
                "message": question,
                "internal_token": token,
            },
        )
        resp.raise_for_status()
        return resp.json()


# ── LLM judge ────────────────────────────────────────────────────────────────

def judge_answer(answer: str, required_keywords: list[str], question: str) -> tuple[float, str]:
    """
    Use GPT-4o as a judge to score whether the answer covers the required facts.

    Scoring rubric:
      1.0 — all keywords present (exact match or accepted clinical synonym)
      0.5 — some keywords present, others missing
      0.0 — no keywords present, OR answer contains fabricated facts

    Returns (score, explanation).
    """
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    prompt = f"""You are evaluating a clinical AI assistant's answer for factual coverage.

Question asked: {question}

Required facts (must appear — exact name or an accepted clinical synonym counts):
{json.dumps(required_keywords, indent=2)}

Agent's answer:
{answer}

Score the answer strictly:
  1.0 — every required fact is present (exact or synonym accepted)
  0.5 — at least one required fact is present but at least one is missing
  0.0 — none of the required facts are present, OR the answer contains
         fabricated information that is NOT in the required facts list

Reply with JSON only, no extra text:
{{"score": 0.0, "explanation": "one sentence reason"}}"""

    response = llm.invoke(prompt)

    # .content may be a string or a list of content blocks (newer OpenAI SDK)
    raw = response.content
    if isinstance(raw, list):
        raw = " ".join(block.get("text", "") if isinstance(block, dict) else str(block) for block in raw)

    # Strip markdown code fences if the model wrapped the JSON
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        data = json.loads(raw)
        return float(data["score"]), data["explanation"]
    except Exception as exc:
        return 0.0, f"Failed to parse judge response: {exc} | raw={raw[:80]!r}"


# ── LangSmith dataset setup ───────────────────────────────────────────────────

def ensure_langsmith_dataset(client: Client, cases: list[dict], dataset_name: str) -> str:
    """
    Create the named dataset in LangSmith if it doesn't exist yet.
    If it already exists, returns the existing dataset ID.
    """
    try:
        dataset = client.create_dataset(
            dataset_name,
            description="Clinical Co-Pilot Q&A pairs for behavioral eval",
        )
        print(f"[langsmith] Created dataset '{dataset_name}' (id={dataset.id})")

        client.create_examples(
            inputs=[{"pid": c["pid"], "question": c["question"]} for c in cases],
            outputs=[{"required_keywords": c["required_keywords"]} for c in cases],
            metadata=[{"id": c["id"], "description": c["description"]} for c in cases],
            dataset_id=dataset.id,
        )
        print(f"[langsmith] Uploaded {len(cases)} examples to dataset")
        return str(dataset.id)

    except Exception:
        # Dataset already exists — look it up
        datasets = list(client.list_datasets(dataset_name=dataset_name))
        if datasets:
            print(f"[langsmith] Dataset '{dataset_name}' already exists (id={datasets[0].id})")
            return str(datasets[0].id)
        raise


# ── Main eval loop ────────────────────────────────────────────────────────────

async def run_evals(dataset_path: Path) -> None:
    if not dataset_path.exists():
        print(f"ERROR: Dataset not found: {dataset_path}")
        sys.exit(1)

    # Derive LangSmith dataset name from filename
    # dataset.json → "clinical-copilot-ground-truth"
    # dataset_persona.json → "clinical-copilot-persona"
    stem = dataset_path.stem  # e.g. "dataset" or "dataset_persona"
    suffix = stem.replace("dataset", "").lstrip("_") or "ground-truth"
    langsmith_dataset_name = f"clinical-copilot-{suffix}"

    cases = json.loads(dataset_path.read_text())
    print(f"Dataset: {dataset_path.name}  ({len(cases)} cases)")

    # Verify service is up before starting
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(f"{AI_SERVICE_URL}/health")
            resp.raise_for_status()
        except Exception as exc:
            print(f"ERROR: AI service not reachable at {AI_SERVICE_URL}: {exc}")
            sys.exit(1)

    langsmith_client = Client()
    dataset_id = ensure_langsmith_dataset(langsmith_client, cases, langsmith_dataset_name)

    # Experiment name — includes timestamp so each run is distinct in LangSmith
    experiment_name = f"eval-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    print(f"\nRunning {len(cases)} eval cases (experiment: {experiment_name})\n")
    print(f"{'ID':<20} {'SCORE':<7} {'STATUS':<10} EXPLANATION")
    print("-" * 80)

    results = []

    for case in cases:
        # 1. Call the live agent
        try:
            response = await call_agent(case["pid"], case["question"])
            answer = response["answer"]
            verification_status = response.get("verification_status", "unknown")
        except Exception as exc:
            answer = ""
            verification_status = "error"
            print(f"{'  ERROR calling agent':<50} {exc}")

        # 2. Judge the answer
        score, explanation = judge_answer(answer, case["required_keywords"], case["question"])

        # 3. Log to LangSmith as a traced run with feedback
        run_id = str(uuid.uuid4())
        try:
            langsmith_client.create_run(
                id=run_id,
                name=case["id"],
                run_type="chain",
                project_name=LANGSMITH_PROJECT,
                inputs={"pid": case["pid"], "question": case["question"]},
                outputs={
                    "answer": answer,
                    "verification_status": verification_status,
                },
                extra={
                    "experiment": experiment_name,
                    "dataset_id": dataset_id,
                    "description": case["description"],
                },
            )
            langsmith_client.create_feedback(
                run_id=run_id,
                key="keyword_coverage",
                score=score,
                comment=explanation,
            )
        except Exception as exc:
            # LangSmith logging is best-effort — eval still runs
            print(f"  [langsmith] Warning: failed to log run {case['id']}: {exc}")

        # 4. Collect result
        passed = score >= 0.5
        results.append({"case": case, "score": score, "passed": passed, "answer": answer})

        status_str = "PASS" if passed else "FAIL"
        print(f"{case['id']:<20} {score:<7.1f} {status_str:<10} {explanation[:60]}")

    # ── Summary ───────────────────────────────────────────────────────────────
    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    pass_rate = passed_count / total

    print("\n" + "=" * 80)
    print(f"RESULTS: {passed_count}/{total} passed  ({pass_rate:.0%} pass rate)")
    print(f"THRESHOLD: {PASS_THRESHOLD:.0%}")

    if results:
        avg_score = sum(r["score"] for r in results) / total
        print(f"AVERAGE SCORE: {avg_score:.2f}")

    failures = [r for r in results if not r["passed"]]
    if failures:
        print("\nFAILED CASES:")
        for r in failures:
            print(f"  [{r['case']['id']}] {r['case']['question']}")
            print(f"    Required: {r['case']['required_keywords']}")
            print(f"    Answer:   {r['answer'][:120]}...")

    print(f"\nLangSmith experiment '{experiment_name}' logged to project '{LANGSMITH_PROJECT}' (dataset: {langsmith_dataset_name})")

    if pass_rate < PASS_THRESHOLD:
        print(f"\nFAILED: pass rate {pass_rate:.0%} is below threshold {PASS_THRESHOLD:.0%}")
        sys.exit(1)
    else:
        print(f"\nPASSED: {pass_rate:.0%} >= {PASS_THRESHOLD:.0%} threshold")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Clinical Co-Pilot behavioral evals")
    parser.add_argument(
        "--dataset",
        default="dataset.json",
        help="Dataset file to run (default: dataset.json). Use dataset_persona.json for USERS.md persona evals.",
    )
    args = parser.parse_args()
    asyncio.run(run_evals(EVALS_DIR / args.dataset))
