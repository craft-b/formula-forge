"""Live eval for LLM generation quality, with regression gates.

`golden_formulas.json` feeds fixed formulas to the deterministic validator, so
it guards the domain math. Nothing guards the half of the system that is a
language model: a prompt edit, a temperature change or a Groq model
deprecation could degrade generation badly and every test would still pass,
because CI mocks every LLM call.

This closes that. It runs in two modes:

**Offline** (`--offline`) scores the deterministic routing layer — intent
detection and constraint-module detection — against labelled briefs. No API
key, no cost, no nondeterminism, so it belongs in PR CI. It is also the more
safety-critical half: if a renal brief fails to activate the renal ruleset,
the formula is never checked against it and passes silently.

**Live** (default) additionally runs real generation through the production
path in `generation.parse_and_validate` and scores what comes back. Costs
money and varies run to run, so it belongs in a nightly job.

Rates are reported with a Wilson 95% interval, because at these sample sizes a
few points of movement is usually noise and a gate that fires on noise gets
switched off within a week. `check_gate` therefore asks whether this run has
dropped below the interval the baseline recorded, not merely below the baseline
number — see its docstring for why that distinction decides whether the gate
survives contact with a nondeterministic model.

    python -m eval.live_eval --offline
    python -m eval.live_eval --json results.json
    python -m eval.live_eval --gate                 # non-zero exit on regression
    python -m eval.live_eval --update-baseline
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

BRIEFS = HERE / "briefs.json"
BASELINE = HERE / "baseline.json"


# ── statistics ────────────────────────────────────────────────────────────────

def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Point estimate and Wilson score interval for a proportion.

    Wilson rather than the normal approximation because these samples are small
    and the rates sit near 1.0, exactly where the normal interval misbehaves —
    it happily reports an upper bound above 100% and a zero-width interval at
    a perfect score.
    """
    if n == 0:
        return 0.0, 0.0, 0.0
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, centre - margin), min(1.0, centre + margin)


@dataclass
class Rate:
    """One measured proportion, with the interval that says whether it moved."""

    name: str
    successes: int
    n: int
    note: str = ""

    @property
    def point(self) -> float:
        return wilson(self.successes, self.n)[0]

    @property
    def low(self) -> float:
        return wilson(self.successes, self.n)[1]

    @property
    def high(self) -> float:
        return wilson(self.successes, self.n)[2]

    def as_dict(self) -> dict:
        return {"name": self.name, "successes": self.successes, "n": self.n,
                "point": round(self.point, 4), "ci_low": round(self.low, 4),
                "ci_high": round(self.high, 4), "note": self.note}


# ── case results ──────────────────────────────────────────────────────────────

@dataclass
class CaseResult:
    id: str
    category: str
    brief: str
    # Routing (offline).
    modules_expected: list[str] = field(default_factory=list)
    modules_detected: list[str] = field(default_factory=list)
    modules_ok: bool = False
    intent_expected: str = ""
    intent_detected: str = ""
    intent_ok: bool = False
    # Generation (live only).
    generated: Optional[bool] = None
    resolved: Optional[bool] = None
    gate_passed_first: Optional[bool] = None
    gate_passed_after_repair: Optional[bool] = None
    numeric_claim_in_prose: Optional[bool] = None
    violations: list[str] = field(default_factory=list)
    error: str = ""
    seconds: float = 0.0


def load_cases() -> list[dict]:
    return json.loads(BRIEFS.read_text(encoding="utf-8"))["cases"]


# ── scoring ───────────────────────────────────────────────────────────────────

def score_routing(cases: list[dict]) -> list[CaseResult]:
    """Intent and module detection. Deterministic — no model involved."""
    from graph import detect_intent, detect_modules

    results = []
    for case in cases:
        detected = sorted(detect_modules(case["brief"]))
        expected = sorted(case["expect_modules"])
        intent = detect_intent(case["brief"])
        results.append(CaseResult(
            id=case["id"], category=case["category"], brief=case["brief"],
            modules_expected=expected, modules_detected=detected,
            modules_ok=detected == expected,
            intent_expected=case["expect_intent"], intent_detected=intent,
            intent_ok=intent == case["expect_intent"],
        ))
    return results


def score_generation(cases: list[dict], results: list[CaseResult],
                     repair: bool = True) -> None:
    """Run real generation for every case that should produce a formula.

    Uses the modules the router actually detected, not the labelled ones: the
    point is to measure the system as it behaves, and a routing miss really
    does mean the ruleset is not enforced downstream.
    """
    from generation import parse_and_validate
    from graph import build_formula_messages, regenerate_formula, _invoke_formula

    by_id = {r.id: r for r in results}
    for case in cases:
        result = by_id[case["id"]]
        if case["expect_gate_pass"] is None:
            continue  # Not a formulation request; routing is the whole test.

        modules = result.modules_detected
        started = time.time()
        try:
            raw = _invoke_formula(build_formula_messages(case["brief"], modules=modules))
            validated = parse_and_validate(raw, modules)
            result.generated = validated is not None
            if validated is None:
                result.error = "unparseable"
                continue

            result.resolved = validated.type == "formula"
            if not result.resolved:
                result.error = "unresolved ingredients"
                result.gate_passed_first = False
            else:
                result.gate_passed_first = validated.validation.passed
                result.numeric_claim_in_prose = validated.notes_contain_numeric_claims
                result.violations = [
                    v.rule_id for v in validated.validation.violations
                    if v.severity == "error"
                ]

            if repair and not result.gate_passed_first:
                feedback = _repair_feedback(validated)
                retry_raw = regenerate_formula(case["brief"], feedback, modules=modules)
                retry = parse_and_validate(retry_raw, modules)
                result.gate_passed_after_repair = bool(
                    retry is not None and retry.type == "formula"
                    and retry.validation.passed)
        except Exception as exc:  # noqa: BLE001 - a live run must not abort mid-set
            result.error = f"{type(exc).__name__}: {exc}"
        finally:
            result.seconds = round(time.time() - started, 2)


def _repair_feedback(validated) -> str:
    """Repair instructions from a failed attempt, mirroring the API's retry."""
    if validated is None or validated.type != "formula":
        return "The formula could not be resolved against the ingredient library."
    lines = [
        f"- {v.rule_id}: measured {v.measured}, limit {v.limit}. {v.explanation}"
        for v in validated.validation.violations if v.severity == "error"
    ]
    return "\n".join(lines) or "The formula failed validation."


def summarise(cases: list[dict], results: list[CaseResult], live: bool) -> list[Rate]:
    by_id = {c["id"]: c for c in cases}
    rates = [
        Rate("intent_routing", sum(r.intent_ok for r in results), len(results),
             "brief routed to the right agent"),
        Rate("module_detection", sum(r.modules_ok for r in results), len(results),
             "constraint rulesets activated exactly as labelled"),
    ]

    constrained = [r for r in results if r.modules_expected]
    if constrained:
        rates.append(Rate(
            "module_detection_constrained",
            sum(r.modules_ok for r in constrained), len(constrained),
            "same, restricted to briefs that carry a clinical constraint"))

    if not live:
        return rates

    attempted = [r for r in results if by_id[r.id]["expect_gate_pass"] is not None]
    generated = [r for r in attempted if r.generated]
    rates += [
        Rate("schema_valid", sum(bool(r.generated) for r in attempted), len(attempted),
             "model output parsed into a candidate"),
        Rate("grounded", sum(bool(r.resolved) for r in generated), len(generated),
             "every ingredient resolved to the governed library"),
    ]

    should_pass = [r for r in attempted if by_id[r.id]["expect_gate_pass"] is True]
    rates.append(Rate(
        "gate_pass_first_try", sum(bool(r.gate_passed_first) for r in should_pass),
        len(should_pass), "cleared validation with no repair"))

    failed_first = [r for r in should_pass if r.gate_passed_first is False]
    if failed_first:
        rates.append(Rate(
            "repair_recovery", sum(bool(r.gate_passed_after_repair) for r in failed_first),
            len(failed_first), "of those that failed, recovered in one repair"))

    constrained_pass = [r for r in should_pass if r.modules_expected]
    if constrained_pass:
        rates.append(Rate(
            "constraint_targeting",
            sum(bool(r.gate_passed_first) for r in constrained_pass),
            len(constrained_pass),
            "designed to the limits rather than being rescued by the gate"))

    checked = [r for r in generated if r.numeric_claim_in_prose is not None]
    if checked:
        rates.append(Rate(
            "prose_free_of_numeric_claims",
            sum(not r.numeric_claim_in_prose for r in checked), len(checked),
            "notes assert no quantity the system did not compute"))

    must_fail = [r for r in attempted if by_id[r.id]["expect_gate_pass"] is False]
    if must_fail:
        rates.append(Rate(
            "unsatisfiable_caught", sum(r.gate_passed_first is False for r in must_fail),
            len(must_fail), "impossible briefs did not yield a passing formula"))

    return rates


# ── reporting ─────────────────────────────────────────────────────────────────

def render(rates: list[Rate], results: list[CaseResult], live: bool) -> str:
    out = ["# Live eval", ""]
    out.append(f"{len(results)} briefs · mode: {'live' if live else 'offline (routing only)'}")
    out.append("")
    out.append("| Metric | Rate | 95% CI | n | Meaning |")
    out.append("|---|---:|---|---:|---|")
    for r in rates:
        out.append(f"| `{r.name}` | {r.point:.0%} | {r.low:.0%}–{r.high:.0%} "
                   f"| {r.n} | {r.note} |")
    out.append("")

    misroutes = [r for r in results if not r.intent_ok]
    if misroutes:
        out += ["## Intent misroutes", "",
                "| Case | Brief | Wanted | Got |", "|---|---|---|---|"]
        out += [f"| `{r.id}` | {r.brief[:58]} | {r.intent_expected} | {r.intent_detected} |"
                for r in misroutes]
        out.append("")

    missed = [r for r in results if not r.modules_ok]
    if missed:
        out += ["## Module detection misses", "",
                "| Case | Wanted | Got |", "|---|---|---|"]
        out += [f"| `{r.id}` | {r.modules_expected or '—'} | {r.modules_detected or '—'} |"
                for r in missed]
        out.append("")

    if live:
        problems = [r for r in results
                    if r.error or r.gate_passed_first is False or r.resolved is False]
        if problems:
            out += ["## Generation problems", "",
                    "| Case | Issue | Violations |", "|---|---|---|"]
            for r in problems:
                issue = r.error or ("gate failed" if r.gate_passed_first is False else "")
                recovered = " (repaired)" if r.gate_passed_after_repair else ""
                out.append(f"| `{r.id}` | {issue}{recovered} "
                           f"| {', '.join(r.violations) or '—'} |")
            out.append("")
    return "\n".join(out)


# ── gating ────────────────────────────────────────────────────────────────────

#: Below this many observations a rate is too noisy to gate on at all.
MIN_GATE_SAMPLE = 8


def check_gate(rates: list[Rate], baseline: dict) -> list[str]:
    """Regressions relative to the recorded baseline.

    Fails when this run's point estimate falls below the *lower* confidence
    bound the baseline recorded — "you are now below where the baseline
    plausibly was", rather than "you are below the baseline", which is a
    different and much twitchier question.

    The distinction matters most at the top of the scale, which is where these
    rates live. Comparing against the baseline point instead would mean a
    baseline of 46/46 fails on the very next run that scores 45/46, and a gate
    that cries wolf on one unlucky sample gets disabled within a week. A
    baseline missing its interval falls back to the point estimate so older
    files still gate.
    """
    failures = []
    for rate in rates:
        prior = baseline.get("rates", {}).get(rate.name)
        if prior is None:
            continue  # New metric: nothing to compare against yet.
        if rate.n < MIN_GATE_SAMPLE:
            continue
        floor = prior.get("ci_low", prior["point"])
        if rate.point < floor - 1e-9:
            failures.append(
                f"{rate.name}: {rate.point:.0%} (n={rate.n}) below the baseline's "
                f"lower bound {floor:.0%} (baseline point {prior['point']:.0%})")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true",
                        help="Routing only. No API key, no cost, deterministic.")
    parser.add_argument("--no-repair", action="store_true",
                        help="Skip the repair re-prompt (halves the API calls).")
    parser.add_argument("--json", type=Path, help="Write full per-case results here.")
    parser.add_argument("--markdown", type=Path, help="Write the report here.")
    parser.add_argument("--gate", action="store_true",
                        help="Exit non-zero if a rate regressed against the baseline.")
    parser.add_argument("--update-baseline", action="store_true",
                        help="Record this run as the new baseline.")
    parser.add_argument("--only", help="Run one category only.")
    args = parser.parse_args()

    cases = load_cases()
    if args.only:
        cases = [c for c in cases if c["category"] == args.only]
        if not cases:
            print(f"No cases in category {args.only!r}")
            return 1

    live = not args.offline
    if live and not os.getenv("GROQ_API_KEY"):
        print("GROQ_API_KEY is not set. Use --offline to score routing only.")
        return 1

    results = score_routing(cases)
    if live:
        score_generation(cases, results, repair=not args.no_repair)

    rates = summarise(cases, results, live)
    report = render(rates, results, live)
    print(report)

    if args.markdown:
        args.markdown.write_text(report + "\n", encoding="utf-8")

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "live" if live else "offline",
        "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile") if live else None,
        "n_cases": len(cases),
        "rates": {r.name: r.as_dict() for r in rates},
        "cases": [asdict(r) for r in results],
    }
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if args.update_baseline:
        BASELINE.write_text(json.dumps(
            {k: payload[k] for k in ("generated_at", "mode", "model", "n_cases", "rates")},
            indent=2), encoding="utf-8")
        print(f"\nBaseline updated: {BASELINE.name}")

    if args.gate:
        if not BASELINE.exists():
            print("\nNo baseline recorded; nothing to gate against. "
                  "Run with --update-baseline first.")
            return 0
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        failures = check_gate(rates, baseline)
        if failures:
            print("\nEVAL GATE FAILED\n")
            for f in failures:
                print(f"  {f}")
            return 1
        print("\nEval gate passed — no rate regressed beyond sampling error.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
