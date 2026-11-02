# PatchPilot — Evaluation and Benchmark Pipeline

This directory contains a synthetic dataset. No reproducible comparative performance experiment is currently implemented. Earlier scores were hardcoded and are withdrawn.

## Structure

- `datasets/synthetic_benchmark.json`: Curated benchmark cases with ground-truth defect lines and failing regression tests.
- `evaluation/evaluate_agent.py`: Reports dataset size and `NOT_MEASURED`; it does not calculate performance metrics.
- `evaluation/evaluation_results.json`: Explicit unmeasured status.

## Reproduction Command

Run the evaluation script with Python:

```powershell
python training/evaluation/evaluate_agent.py
```
