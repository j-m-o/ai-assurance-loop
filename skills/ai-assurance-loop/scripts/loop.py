#!/usr/bin/env python3
"""AI Assurance Loop: a deterministic controller for eval-driven improvement loops.

The proposer (an AI agent or a person) suggests a change. This controller,
not the proposer, decides whether the change is kept and whether the loop
continues. It grades every candidate on a dev set, guards against regressions
and overfitting with a hidden holdout set, enforces hard stop conditions and a
budget, keeps an append-only ledger, and ends at a human promotion gate.

Read-only toward the system under test. Standard library only. No network access.

AI Assurance Loop, created by Jessica Mosley | LinkedIn: https://www.linkedin.com/in/jessmosley/ | GitHub: https://github.com/j-m-o/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reference_sut  # noqa: E402

HERE = Path(__file__).resolve().parents[1]


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def save(p, obj):
    Path(p).write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:12]


def grade(case: dict, response: str) -> list[str]:
    """Return a list of failure reasons; empty means pass."""
    fails = []
    r = response.lower()
    for s in case.get("must_contain", []):
        if s.lower() not in r:
            fails.append(f"missing '{s}'")
    for s in case.get("must_not_contain", []):
        if s.lower() in r:
            fails.append(f"contains forbidden '{s}'")
    for pat in case.get("must_match", []):
        if not re.search(pat, response, re.I):
            fails.append(f"does not match /{pat}/")
    return fails


def evaluate(cases: list[dict], responses: dict[str, str]) -> dict:
    results = {}
    for c in cases:
        resp = responses.get(c["id"])
        reasons = ["no response produced"] if resp is None else grade(c, resp)
        results[c["id"]] = {"pass": not reasons, "critical": bool(c.get("critical")), "category": c.get("category"), "reasons": reasons}
    n = len(results)
    passed = sum(r["pass"] for r in results.values())
    return {"score": round(passed / n, 3) if n else 0.0, "passed": passed, "total": n,
            "critical_failures": sorted(k for k, r in results.items() if r["critical"] and not r["pass"]), "cases": results}


def responses_for(candidate: dict | None, outputs: dict | None, cases: list[dict]) -> dict:
    if outputs is not None:
        return outputs
    return {c["id"]: reference_sut.reply(c["input"], candidate) for c in cases}


def init(args):
    cfg = load(args.config)
    dev, hold = load(args.dataset), load(args.holdout)
    base = load(args.baseline) if args.baseline else None
    outs_dev = load(args.baseline_outputs)["dev"] if args.baseline_outputs else None
    outs_hold = load(args.baseline_outputs)["holdout"] if args.baseline_outputs else None
    d = evaluate(dev, responses_for(base, outs_dev, dev))
    h = evaluate(hold, responses_for(base, outs_hold, hold))
    ledger = {"config": cfg, "dataset": str(Path(args.dataset).resolve()), "holdout": str(Path(args.holdout).resolve()),
              "status": "RUNNING", "budget_used": len(dev) + len(hold), "rejections_in_a_row": 0,
              "best": {"iteration": 0, "candidate": base, "candidate_id": digest(base or outs_dev), "dev": d, "holdout_score": h["score"],
                       "holdout_critical_failures": len(h["critical_failures"])},
              "iterations": [{"iteration": 0, "candidate_id": digest(base or outs_dev), "note": "baseline", "decision": "BASELINE",
                              "dev_score": d["score"], "holdout_score": h["score"], "critical_failures": d["critical_failures"],
                              "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}]}
    save(args.ledger, ledger)
    return ledger, feedback(ledger)


def feedback(ledger: dict) -> dict:
    """What the proposer is allowed to see: dev failures only, never holdout details."""
    best = ledger["best"]
    return {"status": ledger["status"], "best_iteration": best["iteration"], "dev_score": best["dev"]["score"],
            "holdout_score": best["holdout_score"],
            "failing_dev_cases": {k: v["reasons"] for k, v in best["dev"]["cases"].items() if not v["pass"]},
            "critical_failures": best["dev"]["critical_failures"],
            "budget_remaining": ledger["config"]["budget_case_evals"] - ledger["budget_used"]}


def step(args):
    ledger = load(args.ledger)
    cfg = ledger["config"]
    if ledger["status"] != "RUNNING":
        return ledger, {"status": ledger["status"], "message": "Loop already stopped. Start a new ledger to continue."}
    dev, hold = load(ledger["dataset"]), load(ledger["holdout"])
    cand = load(args.candidate) if args.candidate else None
    outs = load(args.outputs) if args.outputs else None
    note = (cand or {}).get("_change_note") or args.note or "unspecified change"
    d = evaluate(dev, responses_for(cand, outs["dev"] if outs else None, dev))
    h = evaluate(hold, responses_for(cand, outs["holdout"] if outs else None, hold))
    ledger["budget_used"] += len(dev) + len(hold)
    best = ledger["best"]

    regressions = sorted(k for k, v in d["cases"].items() if best["dev"]["cases"][k]["pass"] and not v["pass"])
    fixed = sorted(k for k, v in d["cases"].items() if not best["dev"]["cases"][k]["pass"] and v["pass"])
    reasons = []
    if d["score"] < best["dev"]["score"] + cfg["min_improvement"]:
        reasons.append(f"dev score {d['score']} does not beat best {best['dev']['score']} by {cfg['min_improvement']}")
    if regressions:
        reasons.append(f"regresses previously passing cases {regressions}")
    if len(d["critical_failures"]) > len(best["dev"]["critical_failures"]):
        reasons.append("adds critical (safety) failures")
    if h["score"] < best["holdout_score"] - cfg["holdout_tolerance"]:
        reasons.append("holdout score dropped: likely overfitting to the dev set")
    if len(h["critical_failures"]) > best["holdout_critical_failures"]:
        reasons.append("adds critical failures on holdout")

    decision = "REJECTED" if reasons else "ACCEPTED"
    it = len(ledger["iterations"])
    if decision == "ACCEPTED":
        ledger["best"] = {"iteration": it, "candidate": cand, "candidate_id": digest(cand or outs), "dev": d,
                          "holdout_score": h["score"], "holdout_critical_failures": len(h["critical_failures"])}
        ledger["rejections_in_a_row"] = 0
    else:
        ledger["rejections_in_a_row"] += 1
    ledger["iterations"].append({"iteration": it, "candidate_id": digest(cand or outs), "note": note, "decision": decision,
                                 "dev_score": d["score"], "holdout_score": h["score"], "critical_failures": d["critical_failures"],
                                 "fixed": fixed, "regressions": regressions, "rejection_reasons": reasons,
                                 "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})

    b = ledger["best"]
    target = cfg["target"]
    if b["dev"]["score"] >= target["dev_score"] and not b["dev"]["critical_failures"] and b["holdout_score"] >= target["holdout_score"] and b["holdout_critical_failures"] == 0:
        ledger["status"] = "STOP_TARGET_MET_AWAITING_HUMAN_PROMOTION"
    elif it >= cfg["max_iterations"]:
        ledger["status"] = "STOP_MAX_ITERATIONS"
    elif ledger["rejections_in_a_row"] >= cfg["patience"]:
        ledger["status"] = "STOP_PLATEAU"
    elif ledger["budget_used"] + len(dev) + len(hold) > cfg["budget_case_evals"]:
        ledger["status"] = "STOP_BUDGET"
    save(args.ledger, ledger)
    fb = feedback(ledger)
    fb.update(decision=decision, iteration=it, fixed=fixed, regressions=regressions, rejection_reasons=reasons)
    return ledger, fb


def report(ledger: dict) -> str:
    L = ["# AI Assurance Loop Ledger", "", f"**Status:** {ledger['status']}  ",
         f"**Best iteration:** {ledger['best']['iteration']} (candidate `{ledger['best']['candidate_id']}`)  ",
         f"**Budget used:** {ledger['budget_used']} of {ledger['config']['budget_case_evals']} case evaluations", "",
         "| # | Change | Decision | Dev | Holdout | Fixed | Regressions | Why rejected |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for i in ledger["iterations"]:
        L.append(f"| {i['iteration']} | {i['note']} | {i['decision']} | {i['dev_score']} | {i['holdout_score']} | "
                 f"{', '.join(i.get('fixed', [])) or '-'} | {', '.join(i.get('regressions', [])) or '-'} | {'; '.join(i.get('rejection_reasons', [])) or '-'} |")
    if ledger["status"].startswith("STOP_TARGET_MET"):
        L += ["", "## Human promotion gate", "",
              "The loop met its targets. It does not promote. A named owner reviews before anything ships:", "",
              "- [ ] Read the diff between baseline and best candidate", "- [ ] Spot-check failing and borderline replies by hand",
              "- [ ] Confirm the dev and holdout sets still represent real traffic", "- [ ] Record approver, date and rollback plan"]
    return "\n".join(L) + "\n"


def demo(args):
    d = HERE / "assets" / "demo"
    ledger_path = Path(args.ledger)
    ns = argparse.Namespace(config=d / "loop-config.json", dataset=d / "dev.json", holdout=d / "holdout.json",
                            baseline=d / "candidates" / "v0-baseline.json", baseline_outputs=None, ledger=ledger_path)
    init(ns)
    for c in sorted((d / "candidates").glob("c*.json")):
        ledger, fb = step(argparse.Namespace(ledger=ledger_path, candidate=c, outputs=None, note=None))
        if ledger["status"] != "RUNNING":
            break
    return load(ledger_path)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init", help="Grade the baseline and start a ledger")
    i.add_argument("--config", required=True)
    i.add_argument("--dataset", required=True)
    i.add_argument("--holdout", required=True)
    i.add_argument("--baseline", help="Config for the reference SUT")
    i.add_argument("--baseline-outputs", help='Your system\'s replies: {"dev": {id: text}, "holdout": {id: text}}')
    i.add_argument("--ledger", required=True)
    s = sub.add_parser("step", help="Grade one candidate and decide")
    s.add_argument("--ledger", required=True)
    s.add_argument("--candidate", help="Config for the reference SUT")
    s.add_argument("--outputs", help="Your system's replies for this candidate")
    s.add_argument("--note", help="One-line description of the change")
    r = sub.add_parser("report", help="Render the ledger")
    r.add_argument("--ledger", required=True)
    m = sub.add_parser("demo", help="Run the fictional demo end to end")
    m.add_argument("--ledger", default="demo-ledger.json")
    a = p.parse_args()
    if a.cmd == "init":
        _, fb = init(a)
        print(json.dumps(fb, indent=2))
    elif a.cmd == "step":
        _, fb = step(a)
        print(json.dumps(fb, indent=2))
    elif a.cmd == "report":
        print(report(load(a.ledger)))
    else:
        print(report(demo(a)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
