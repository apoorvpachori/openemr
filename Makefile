# Clinical Co-Pilot — development shortcuts
# Run from repo root.

.PHONY: checks checks-fast checks-verbose

## Run all 4 test/eval layers and print a quality gate report.
checks:
	python3 ai-service/run_checks.py

## Same as `checks` but skip the LangSmith eval layers (faster, no LLM cost).
checks-fast:
	python3 ai-service/run_checks.py --fast

## Like `checks` but prints the raw output from every layer.
checks-verbose:
	python3 ai-service/run_checks.py --verbose
