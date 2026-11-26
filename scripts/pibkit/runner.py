"""Execute checks from tests/matrix.yaml and aggregate results."""

from __future__ import annotations

import datetime as dt
import json
import platform
import sys
import time
from pathlib import Path

import yaml

from .core import FAIL, NO_TARGETS, NOT_RUN, PASS, REPO_ROOT, Result, ToolMissing, install_hint, select
from .handlers import HANDLERS

MATRIX = REPO_ROOT / "tests" / "matrix.yaml"
RESULTS_DIR = REPO_ROOT / "reports" / "generated"
COLORS = {PASS: "\033[32m", FAIL: "\033[31m", NOT_RUN: "\033[33m", NO_TARGETS: "\033[36m"}


def load_matrix() -> dict:
    return yaml.safe_load(MATRIX.read_text(encoding="utf-8"))


def run_check(check: dict) -> Result:
    files = select(check.get("include", ["**"]), check.get("exclude"))
    result = Result(check["id"], check["stage"], NO_TARGETS, targets=len(files))
    if not files and check.get("mode") != "once":
        result.details = ["no files matched include patterns"]
        return result
    handler = HANDLERS[check["handler"]]
    start = time.monotonic()
    try:
        status, details = handler(check, files)
    except ToolMissing as exc:
        status, details = NOT_RUN, [f"required tool '{exc.tool}' not available. Install: {install_hint(exc.tool)}"]
    except Exception as exc:  # a crashing check is a failure, never a pass
        status, details = FAIL, [f"check crashed: {type(exc).__name__}: {exc}"]
    result.status, result.details, result.duration_s = status, details, time.monotonic() - start
    return result


def colour(status: str) -> str:
    if not sys.stdout.isatty():
        return status
    return f"{COLORS.get(status, '')}{status}\033[0m"


def execute(stages: list[str], only: list[str] | None, strict: bool, verbose: bool) -> int:
    matrix = load_matrix()
    checks = [c for c in matrix["checks"] if c["stage"] in stages and (not only or c["id"] in only)]
    if not checks:
        print(f"no checks selected for stages={stages} only={only}")
        return 2
    results: list[Result] = []
    for check in checks:
        print(f"==> [{check['stage']}] {check['id']}: {check.get('description', '')}", flush=True)
        r = run_check(check)
        results.append(r)
        print(f"    {colour(r.status)}  targets={r.targets}  {r.duration_s:.1f}s", flush=True)
        if r.status in (FAIL, NOT_RUN) or verbose:
            for d in r.details[: 50 if verbose else 25]:
                safe = d.encode("ascii", "replace").decode("ascii")
                print("      " + safe.replace("\n", "\n      "))
    counts = {s: sum(r.status == s for r in results) for s in (PASS, FAIL, NOT_RUN, NO_TARGETS)}
    print("\nSummary: " + "  ".join(f"{colour(k)}={v}" for k, v in counts.items()))
    write_results(stages, results)
    if counts[FAIL]:
        return 1
    if strict and counts[NOT_RUN]:
        print("strict mode: NOT RUN checks are treated as failures")
        return 1
    return 0


def write_results(stages: list[str], results: list[Result]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "environment": {
            "os": platform.platform(),
            "python": platform.python_version(),
        },
        "stages": stages,
        "results": [r.to_dict() for r in results],
    }
    path = RESULTS_DIR / f"results-{'-'.join(stages)}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    # merge into a cumulative file used by the report generator
    cumulative = RESULTS_DIR / "results-latest.json"
    merged = json.loads(cumulative.read_text(encoding="utf-8")) if cumulative.exists() else {"results": {}}
    for r in results:
        merged["results"][r.check_id] = {**r.to_dict(), "generated_at": payload["generated_at"], "environment": payload["environment"]}
    cumulative.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return path


def list_matrix() -> int:
    matrix = load_matrix()
    print(f"{'stage':<18} {'check':<34} {'tools':<28} targets")
    for c in matrix["checks"]:
        n = len(select(c.get("include", ["**"]), c.get("exclude")))
        print(f"{c['stage']:<18} {c['id']:<34} {','.join(c.get('tools', [])) or '-':<28} {n}")
    return 0
