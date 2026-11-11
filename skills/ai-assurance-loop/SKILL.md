---
name: ai-assurance-loop
description: Run a safe, bounded eval-driven improvement loop on an AI feature, prompt or agent. The AI proposes one change at a time; a deterministic controller grades it on a dev set and a hidden holdout set, rejects anything that regresses passing cases, adds safety failures or overfits, enforces stop conditions and a budget, records every iteration in a ledger, and stops at a human promotion gate. Use when someone asks to improve a prompt or agent against evals, iterate until tests pass, build an eval loop, harden an AI feature against prompt injection or PII leaks, or do loop engineering with guardrails. The loop never promotes or ships on its own.
metadata:
  author: Jessica Mosley
  version: 1.0.0
  linkedin: https://www.linkedin.com/in/jessmosley/
  github: https://github.com/j-m-o/
---

# AI Assurance Loop

"Keep going until the evals pass" is the most common loop given to an AI agent, and the most dangerous when it is open-ended. Without guardrails the agent games the graders, trades one fixed case for two silent regressions, overfits to the examples it can see, or spends without limit. This skill splits the loop in two:

- **Proposer (you, the agent):** reads failures and proposes **one** focused change.
- **Controller (`scripts/loop.py`):** decides whether the change is kept and whether the loop continues. You do not override it.

Why the split matters, and the exact acceptance rule, are in `references/loop-design.md`.

## Principles

- **The controller decides, not the proposer.** Accept, reject and stop come from `loop.py`. Never edit the ledger, config, graders or datasets during a run.
- **Targets and budget are set by a human before the loop starts.** If they are missing, ask. Do not invent them.
- **One change per iteration.** Small, attributable changes make the ledger readable and regressions traceable.
- **No regressions.** A candidate that breaks any previously passing case is rejected, even if the total score rises.
- **Safety cases are critical.** Any new critical failure (prompt injection, PII, unsafe promises) rejects the candidate.
- **The holdout set stays hidden.** You see dev failures only. Never ask to see holdout cases or tune toward them.
- **Graders are not ground truth.** A passing score means the graders passed. Say so, and recommend human spot checks.
- **Stop means stop.** At any stop status, report and hand off. Do not start a new ledger to keep going without the person's approval.
- **The loop never promotes.** It ends at `STOP_TARGET_MET_AWAITING_HUMAN_PROMOTION`. A named owner ships or does not.

## Setup

1. Confirm with the person: the system under test, who owns promotion, the target scores, max iterations, patience (rejections in a row before plateau) and budget in case evaluations. Write them into a loop config like `assets/demo/loop-config.json`.
2. Build or confirm the eval sets. Use `references/eval-design.md`. Keep a **dev** set you may read and a **holdout** set you never read. Mark safety cases `"critical": true`.
3. Start the ledger:

```bash
python scripts/loop.py init --config loop-config.json --dataset dev.json --holdout holdout.json \
  --baseline-outputs baseline-outputs.json --ledger ledger.json
```

For your own system, run it over every dev and holdout input yourself and save replies as `{"dev": {id: reply}, "holdout": {id: reply}}`. The controller only grades replies; it never calls your system or the network. The `--baseline` and `--candidate` options exist for the bundled fictional demo system.

## The loop

Repeat until the status is not `RUNNING`:

1. Read the feedback JSON: failing dev cases with reasons, critical failures, budget remaining.
2. Group failures by cause. Pick the single change most likely to fix the largest group **without touching passing behavior**.
3. Apply the change to a copy of the candidate (prompt, config or code). Write a one-line change note.
4. Produce replies for dev and holdout with the changed system.
5. Run the controller:

```bash
python scripts/loop.py step --ledger ledger.json --outputs candidate-outputs.json --note "one-line change"
```

6. If `REJECTED`, read `rejection_reasons`, discard the change, and propose a different one from the **best** candidate, not the rejected one.

## Stop conditions

| Status | Meaning | Your next move |
| --- | --- | --- |
| `STOP_TARGET_MET_AWAITING_HUMAN_PROMOTION` | Dev and holdout targets met with zero critical failures | Present the report and the promotion checklist |
| `STOP_MAX_ITERATIONS` | Iteration cap reached | Report best candidate and remaining failures |
| `STOP_PLATEAU` | Too many rejections in a row | Report; the remaining failures likely need a design change or new data |
| `STOP_BUDGET` | Next iteration would exceed the case-evaluation budget | Report; ask before any new budget |

## Report

```bash
python scripts/loop.py report --ledger ledger.json
```

Present: status, best iteration and its change history, rejected changes and why, remaining failures, and the human promotion checklist. Add one honest sentence on what the graders cannot measure.

## Demo

`python scripts/loop.py demo` runs a fictional support assistant through five proposed changes. Iteration 3 raises the score but breaks a passing case and is rejected. The loop stops at the human gate after iteration 5.

---
*AI Assurance Loop, created by **Jessica Mosley** | [LinkedIn](https://www.linkedin.com/in/jessmosley/) | [GitHub](https://github.com/j-m-o/)*
