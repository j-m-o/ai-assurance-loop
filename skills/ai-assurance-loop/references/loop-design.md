# Loop design notes

## Why the controller is code, not a prompt

An agent asked to judge its own progress has every incentive to declare success. Moving accept, reject and stop decisions into a small deterministic program gives three properties a prompt cannot:

1. **The rules cannot drift** between iterations or model versions.
2. **The proposer cannot negotiate.** A rejection reason is a fact, not an opinion.
3. **The ledger is trustworthy** because the party being judged did not write it.

## Acceptance rule

A candidate is kept only if **all** hold:

- dev score beats the best by at least `min_improvement`
- no previously passing dev case now fails
- critical failures on dev do not increase
- holdout score does not fall more than `holdout_tolerance`
- critical failures on holdout do not increase

Each rejection lists every rule it broke.

## Failure modes this prevents

| Failure mode | Guard |
| --- | --- |
| Trading regressions for wins | No-regression rule |
| Gaming visible examples | Hidden holdout plus tolerance |
| Fixing quality by weakening safety | Critical-case rule |
| Endless iteration | Max iterations, patience, budget |
| Silent self-promotion | Terminal human gate; no promote command |
| Unreviewable history | Append-only ledger with change notes and hashes |

## Tuning

- `patience` of 3 suits most prompt work. Lower it when each iteration is expensive.
- `min_improvement` of one case (1 / dev size) prevents noise-level "wins".
- `holdout_tolerance` of 0 is strict. Raise it slightly only for large, noisy holdout sets, and record why.
