# Hermes Autoresearch — Program Instructions

Inspired by [karpathy/autoresearch](https://github.com/karpathy/autoresearch).

## The Loop

```
LOOP:
  1. Researcher agent proposes ONE change to SOUL.md
  2. Git commit the change
  3. Run eval harness (12 scenarios, ~5 min)
  4. If score improved → KEEP and advance
  5. If score same + simpler → KEEP
  6. If score same or worse → REVERT (git reset)
  7. Log to results.tsv
  8. GOTO 1. NEVER STOP.
```

## Architecture

| File | Role | Mutable? |
|------|------|----------|
| `evals/hermes_eval.py` | Eval harness (the metric) | NO — immutable |
| `evals/scenarios.json` | Test scenarios | NO — immutable |
| `~/.hermes/SOUL.md` | Agent personality & instructions | YES — researcher's playground |
| `scripts/autoresearch.py` | The loop runner | NO — immutable |

## The Metric

Composite score (0.0 - 1.0) across 12 scenarios:
- **Execution score (30%)**: Does Hermes DO the work vs DESCRIBE it?
- **Must-not-contain (25%)**: No forbidden phrases ("you need to", "file picker", etc.)
- **Must-contain (20%)**: Response includes evidence of execution
- **Tool usage (15%)**: Did it use the right tools?
- **Quality (10%)**: Response length and structure

## What the Researcher Can Change

The researcher agent (Sonnet) proposes changes to `SOUL.md` — the system prompt
that defines how Hermes behaves. Changes might include:
- Stronger execution-first instructions
- Better tool usage guidance
- Removing unnecessary text
- Adding platform-specific execution patterns
- Tone and identity adjustments

## Design Principles

1. **One change at a time.** Small, focused, testable.
2. **Fix worst-scoring scenario first.** Targeted improvement.
3. **Simpler is better.** Same score with fewer lines = keep it.
4. **Execution over description.** Every change should push Hermes toward DOING.
5. **Never stop.** ~12 experiments/hour. Run overnight. Wake up to a better agent.

## Running

```bash
# Full loop (runs forever)
python3 scripts/autoresearch.py

# Run 5 experiments
python3 scripts/autoresearch.py --max-runs 5

# Just measure baseline
python3 scripts/autoresearch.py --baseline-only

# Test the harness without API calls
python3 scripts/autoresearch.py --dry-run
```

## Results

All experiments logged to `evals/results.tsv`:
```
timestamp  run  commit  score  prev_score  delta  status  description  elapsed_s  pass_count  fail_count
```

Status values: `baseline`, `keep`, `keep_simpler`, `discard`, `discard_same`, `skip`, `crash`
