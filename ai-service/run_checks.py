#!/usr/bin/env python3
"""
Run every test layer and print a consolidated quality gate report.

Usage (from repo root or ai-service/):
    python ai-service/run_checks.py           # all 4 layers
    python ai-service/run_checks.py --fast    # skip LangSmith evals (layers 1+2 only)
    python ai-service/run_checks.py --verbose # always show raw output

Layers:
    1  — Structural unit tests    (19 tests, ~1s,   no LLM)
    2  — Adversarial integration  (9 tests,  ~25s,  real LLM + mocked DB)
    3a — Factual evals            (10 cases, ~60s,  real LLM + real DB)
    3b — Persona evals / USERS.md (8 cases,  ~60s,  real LLM + real DB)

Exit code: 0 if all gates pass, 1 otherwise.
"""

import argparse
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = REPO_ROOT / "docker-compose.ai.yml"
W = 66  # report width


# ── Result model ──────────────────────────────────────────────────────────────

@dataclass
class LayerResult:
    name: str
    description: str
    passed: int
    total: int
    elapsed: float
    ok: bool
    score: float | None = None   # only set for LangSmith eval layers
    output: str = field(default="", repr=False)


# ── Docker helpers ────────────────────────────────────────────────────────────

def _container_running() -> bool:
    """Return True if the ai service container is up."""
    r = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "ps", "--status", "running", "--quiet"],
        capture_output=True, text=True,
    )
    return bool(r.stdout.strip())


def _exec(args: list[str], timeout: int = 360) -> tuple[int, str, float]:
    """Run a command inside the ai container. Returns (exit_code, combined_output, elapsed_s)."""
    cmd = [
        "docker", "compose", "-f", str(COMPOSE_FILE),
        "exec", "-w", "/app", "ai",
    ] + args
    t0 = time.monotonic()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout + r.stderr, time.monotonic() - t0


# ── Output parsers ────────────────────────────────────────────────────────────

def _parse_pytest(output: str) -> tuple[int, int]:
    """Return (passed, failed) from pytest -q output."""
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", output)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", output)) else 0
    return passed, failed


def _parse_eval(output: str) -> tuple[int, int, float]:
    """Return (passed, total, avg_score) from run_evals.py output."""
    passed, total = 0, 0
    if m := re.search(r"RESULTS: (\d+)/(\d+) passed", output):
        passed, total = int(m.group(1)), int(m.group(2))
    score = float(m.group(1)) if (m := re.search(r"AVERAGE SCORE: ([\d.]+)", output)) else 0.0
    return passed, total, score


# ── Report helpers ────────────────────────────────────────────────────────────

def _bar(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _print_layer(r: LayerResult, verbose: bool) -> None:
    status = f"[{_bar(r.ok)}]"
    print(f"  {status}  {r.name} — {r.description}")

    detail = f"{r.passed}/{r.total}"
    if r.score is not None:
        detail += f"  avg score: {r.score:.2f}"
    detail += f"  ({r.elapsed:.1f}s)"
    print(f"         {detail}")

    if verbose or not r.ok:
        if not r.ok and "FAILED CASES" in r.output:
            relevant = r.output[r.output.find("FAILED CASES"):]
        elif not r.ok:
            relevant = r.output[-2000:]
        else:
            relevant = r.output
        border = "  " + "-" * (W - 4)
        print(border)
        for line in relevant.strip().splitlines():
            print(f"    {line}")
        print(border)

    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Run all Clinical Co-Pilot checks")
    parser.add_argument("--fast", action="store_true", help="Skip LangSmith eval layers (3a + 3b)")
    parser.add_argument("--verbose", action="store_true", help="Always print raw layer output")
    args = parser.parse_args()

    print()
    print("=" * W)
    print("  CLINICAL CO-PILOT — QUALITY GATE REPORT")
    print("=" * W)
    print()

    if not _container_running():
        print("  ERROR: AI service container is not running.")
        print("  Start it with:  docker compose -f docker-compose.ai.yml up -d")
        print()
        sys.exit(1)

    layers: list[LayerResult] = []

    # ── Layer 1: Structural unit tests ────────────────────────────────────────
    print("  Running Layer 1: Structural tests (unit, no LLM)...")
    code, out, elapsed = _exec(
        ["python", "-m", "pytest", "tests/test_structural.py", "-m", "unit", "-q", "--tb=short"],
        timeout=60,
    )
    passed, failed = _parse_pytest(out)
    layers.append(LayerResult(
        name="Layer 1", description="Structural tests (unit, no LLM)",
        passed=passed, total=passed + failed,
        elapsed=elapsed, ok=(code == 0 and failed == 0), output=out,
    ))
    _print_layer(layers[-1], args.verbose)

    # ── Layer 2: Adversarial integration tests ────────────────────────────────
    print("  Running Layer 2: Adversarial tests (real LLM, mocked DB)...")
    code, out, elapsed = _exec(
        ["python", "-m", "pytest", "tests/test_adversarial.py", "-m", "integration", "-q", "--tb=short"],
        timeout=180,
    )
    passed, failed = _parse_pytest(out)
    layers.append(LayerResult(
        name="Layer 2", description="Adversarial tests (real LLM, mocked DB)",
        passed=passed, total=passed + failed,
        elapsed=elapsed, ok=(code == 0 and failed == 0), output=out,
    ))
    _print_layer(layers[-1], args.verbose)

    if not args.fast:
        # ── Layer 3a: Factual evals ───────────────────────────────────────────
        print("  Running Layer 3a: Factual evals (dataset.json)...")
        code, out, elapsed = _exec(
            ["python", "tests/evals/run_evals.py"],
            timeout=360,
        )
        passed, total, score = _parse_eval(out)
        layers.append(LayerResult(
            name="Layer 3a", description="Factual evals (dataset.json)  gate: >=80%",
            passed=passed, total=total,
            elapsed=elapsed, ok=(code == 0), score=score, output=out,
        ))
        _print_layer(layers[-1], args.verbose)

        # ── Layer 3b: Persona evals ───────────────────────────────────────────
        print("  Running Layer 3b: Persona evals (USERS.md / dataset_persona.json)...")
        code, out, elapsed = _exec(
            ["python", "tests/evals/run_evals.py", "--dataset", "dataset_persona.json"],
            timeout=360,
        )
        passed, total, score = _parse_eval(out)
        layers.append(LayerResult(
            name="Layer 3b", description="Persona evals (USERS.md)  gate: >=80%",
            passed=passed, total=total,
            elapsed=elapsed, ok=(code == 0), score=score, output=out,
        ))
        _print_layer(layers[-1], args.verbose)

    # ── Summary ───────────────────────────────────────────────────────────────
    pytest_layers = [r for r in layers if r.score is None]
    eval_layers   = [r for r in layers if r.score is not None]

    total_pytest  = sum(r.total  for r in pytest_layers)
    passed_pytest = sum(r.passed for r in pytest_layers)
    total_evals   = sum(r.total  for r in eval_layers)
    passed_evals  = sum(r.passed for r in eval_layers)
    gates_passed  = sum(1 for r in layers if r.ok)
    total_gates   = len(layers)
    all_pass      = all(r.ok for r in layers)
    total_time    = sum(r.elapsed for r in layers)

    print("=" * W)
    overall = _bar(all_pass)
    print(f"  OVERALL: {overall}")
    print()
    print(f"    pytest tests:  {passed_pytest}/{total_pytest} passed")
    if eval_layers:
        avg_score = sum(r.score for r in eval_layers) / len(eval_layers)
        print(f"    eval cases:    {passed_evals}/{total_evals} passed  (avg score: {avg_score:.2f})")
    print(f"    quality gates: {gates_passed}/{total_gates} passed")
    print(f"    total time:    {total_time:.0f}s")
    if args.fast:
        print()
        print("    (LangSmith eval layers skipped — run without --fast for full report)")
    print("=" * W)
    print()

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
