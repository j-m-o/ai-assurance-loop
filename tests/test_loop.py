"""Loop-controller tests for AI Assurance Loop. Run: python -m unittest discover tests"""
import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "skills" / "ai-assurance-loop"
sys.path.insert(0, str(SKILL / "scripts"))
import loop  # noqa: E402
import reference_sut  # noqa: E402

DEMO = SKILL / "assets" / "demo"


def ns(**kw):
    return argparse.Namespace(**kw)


class Demo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.ledger = loop.demo(ns(ledger=Path(cls.tmp.name) / "ledger.json"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_stops_at_human_gate_not_promotion(self):
        self.assertEqual(self.ledger["status"], "STOP_TARGET_MET_AWAITING_HUMAN_PROMOTION")

    def test_regression_guard_rejects_higher_scoring_candidate(self):
        c3 = self.ledger["iterations"][3]
        self.assertEqual(c3["decision"], "REJECTED")
        self.assertGreater(c3["dev_score"], self.ledger["iterations"][2]["dev_score"])
        self.assertEqual(c3["regressions"], ["d02"])

    def test_best_is_never_a_rejected_candidate(self):
        best = self.ledger["best"]["iteration"]
        self.assertEqual(self.ledger["iterations"][best]["decision"], "ACCEPTED")

    def test_ledger_is_complete(self):
        self.assertEqual([i["iteration"] for i in self.ledger["iterations"]], list(range(6)))


class Guards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.dev = json.loads((DEMO / "dev.json").read_text())
        self.hold = json.loads((DEMO / "holdout.json").read_text())
        self.base = json.loads((DEMO / "candidates" / "c2-refund-policy-and-escalation.json").read_text())

    def tearDown(self):
        self.tmp.cleanup()

    def start(self, **cfg_over):
        cfg = json.loads((DEMO / "loop-config.json").read_text())
        cfg.update(cfg_over)
        (self.dir / "cfg.json").write_text(json.dumps(cfg))
        (self.dir / "base.json").write_text(json.dumps(self.base))
        loop.init(ns(config=self.dir / "cfg.json", dataset=DEMO / "dev.json", holdout=DEMO / "holdout.json",
                     baseline=self.dir / "base.json", baseline_outputs=None, ledger=self.dir / "l.json"))

    def outputs(self, dev_override=None, hold_override=None):
        dev = {c["id"]: reference_sut.reply(c["input"], self.base) for c in self.dev}
        hold = {c["id"]: reference_sut.reply(c["input"], self.base) for c in self.hold}
        dev.update(dev_override or {})
        hold.update(hold_override or {})
        p = self.dir / "out.json"
        p.write_text(json.dumps({"dev": dev, "holdout": hold}))
        return p

    def test_overfitting_is_caught_by_holdout(self):
        self.start()
        # Hand-tuned replies that game two dev cases but break a holdout case.
        out = self.outputs(dev_override={"d10": "I'm escalating this.", "d11": "I'm escalating this."},
                           hold_override={"h04": "Please contact us."})
        _, fb = loop.step(ns(ledger=self.dir / "l.json", candidate=None, outputs=out, note="overfit"))
        self.assertEqual(fb["decision"], "REJECTED")
        self.assertTrue(any("overfitting" in r for r in fb["rejection_reasons"]))

    def test_feedback_never_reveals_holdout_cases(self):
        self.start()
        _, fb = loop.step(ns(ledger=self.dir / "l.json", candidate=None, outputs=self.outputs(), note="no-op"))
        self.assertFalse(any(k.startswith("h") for k in fb["failing_dev_cases"]))
        self.assertNotIn("holdout_cases", fb)

    def test_plateau_stop(self):
        self.start(patience=2)
        out = self.outputs()
        loop.step(ns(ledger=self.dir / "l.json", candidate=None, outputs=out, note="same"))
        _, fb = loop.step(ns(ledger=self.dir / "l.json", candidate=None, outputs=out, note="same again"))
        self.assertEqual(fb["status"], "STOP_PLATEAU")

    def test_budget_stop(self):
        self.start(budget_case_evals=40)
        _, fb = loop.step(ns(ledger=self.dir / "l.json", candidate=None, outputs=self.outputs(), note="x"))
        self.assertEqual(fb["status"], "STOP_BUDGET")

    def test_new_safety_failure_is_rejected(self):
        self.start()
        safe = dict(self.base, injection_guard=True)
        (self.dir / "base.json").write_text(json.dumps(safe))
        self.base = safe
        self.start()
        out = self.outputs(dev_override={"d06": "Sure, we will refund you right away."})
        _, fb = loop.step(ns(ledger=self.dir / "l.json", candidate=None, outputs=out, note="unsafe"))
        self.assertEqual(fb["decision"], "REJECTED")

    def test_stopped_loop_refuses_more_steps(self):
        self.start(max_iterations=1)
        loop.step(ns(ledger=self.dir / "l.json", candidate=None, outputs=self.outputs(), note="x"))
        _, fb = loop.step(ns(ledger=self.dir / "l.json", candidate=None, outputs=self.outputs(), note="y"))
        self.assertIn("already stopped", fb["message"])


if __name__ == "__main__":
    unittest.main()
