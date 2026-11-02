"""Describe the available synthetic dataset without claiming measured performance.

This repository does not contain executable benchmark harnesses for the claimed
single-pass or closed-loop comparisons. Do not synthesize scores here.
"""
import json
from pathlib import Path

BENCHMARK_FILE = Path(__file__).resolve().parent.parent / "datasets" / "synthetic_benchmark.json"
RESULTS_FILE = Path(__file__).resolve().parent / "evaluation_results.json"


def run_evaluation():
    cases = json.loads(BENCHMARK_FILE.read_text(encoding="utf-8"))
    results = {
        "evaluation_status": "NOT_MEASURED",
        "dataset": BENCHMARK_FILE.name,
        "case_count": len(cases),
        "dataset_type": "synthetic",
        "metrics": None,
        "reason": "No reproducible repair benchmark harness exists; previous values were hardcoded and are withdrawn.",
        "failed_cases": None,
        "skipped_cases": len(cases),
        "reproducibility": "No performance experiment was run.",
    }
    RESULTS_FILE.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    run_evaluation()
