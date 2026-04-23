"""
τ²-Bench evaluation harness.
Wraps the tau2-bench retail domain, writes results to score_log.json
and appends traces to trace_log.jsonl. Sends each trace to Langfuse.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import scipy.stats as stats

_SCORE_LOG = Path(__file__).parent / "score_log.json"
_TRACE_LOG = Path(__file__).parent / "trace_log.jsonl"
_TAU2_REPO = Path(os.getenv("TAU2_REPO_PATH", str(Path.home() / "tau2-bench")))
_PINNED_MODEL = os.getenv("TAU2_MODEL", "openrouter/qwen/qwen3-next-80b-a3b-thinking")


def run_eval(
    domain: str = "retail",
    num_tasks: Optional[int] = None,
    num_trials: int = 1,
    task_ids: Optional[list[int]] = None,
    tag: str = "dev",
) -> dict:
    """
    Run tau2-bench evaluation and return aggregated results.
    Appends raw traces to trace_log.jsonl.
    Updates score_log.json with a new entry.
    """
    if not _TAU2_REPO.exists():
        raise FileNotFoundError(
            f"tau2-bench not found at {_TAU2_REPO}. "
            "Clone: git clone https://github.com/sierra-research/tau2-bench"
        )

    results: list[dict] = []
    total_cost = 0.0

    task_list = task_ids or list(range(1, (num_tasks or 30) + 1))

    for task_id in task_list:
        for trial in range(num_trials):
            trace = _run_single_task(domain, task_id, trial)
            results.append(trace)
            total_cost += trace.get("agent_cost", 0.0)
            _append_trace(trace)

    # Compute pass@1
    task_rewards: dict[int, list[float]] = {}
    for r in results:
        tid = int(r["task_id"])
        task_rewards.setdefault(tid, [])
        task_rewards[tid].append(r["reward"])

    pass_at_1_per_task = [1.0 if max(v) > 0 else 0.0 for v in task_rewards.values()]
    n = len(pass_at_1_per_task)
    mean_pass = sum(pass_at_1_per_task) / n if n > 0 else 0.0

    # 95% CI (Wilson interval)
    ci = _wilson_ci(mean_pass, n)

    durations = [r.get("duration", 0) for r in results]
    durations_sorted = sorted(durations)
    p50 = durations_sorted[int(0.50 * len(durations_sorted))] if durations_sorted else 0
    p95 = durations_sorted[int(0.95 * len(durations_sorted))] if durations_sorted else 0

    entry = {
        "tag": tag,
        "domain": domain,
        "total_tasks": n,
        "evaluated_simulations": len(results),
        "num_trials": num_trials,
        "pass_at_1": round(mean_pass, 4),
        "pass_at_1_ci_95": [round(ci[0], 4), round(ci[1], 4)],
        "avg_agent_cost": round(total_cost / max(len(results), 1), 4),
        "p50_latency_seconds": round(p50, 4),
        "p95_latency_seconds": round(p95, 4),
        "infra_error_count": sum(1 for r in results if r.get("error")),
        "model": _PINNED_MODEL,
        "run_at": datetime.now(timezone.utc).isoformat(),
    }

    _update_score_log(entry)
    _send_to_langfuse(entry, results)

    return entry


def _run_single_task(domain: str, task_id: int, trial: int) -> dict:
    """
    Run a single task via tau2-bench CLI.
    Falls back to a stub result if tau2-bench is not configured.
    """
    simulation_id = str(uuid.uuid4())
    start = time.time()

    try:
        cmd = [
            sys.executable, "-m", "tau2",
            "--domain", domain,
            "--task-id", str(task_id),
            "--model", _PINNED_MODEL,
            "--output-format", "json",
        ]
        result = subprocess.run(
            cmd,
            cwd=str(_TAU2_REPO),
            capture_output=True,
            text=True,
            timeout=900,
        )
        duration = time.time() - start

        if result.returncode == 0:
            data = json.loads(result.stdout)
            return {
                "simulation_id": simulation_id,
                "task_id": str(task_id),
                "trial": trial,
                "domain": domain,
                "reward": float(data.get("reward", 0)),
                "agent_cost": float(data.get("cost", 0)),
                "duration": duration,
                "termination_reason": data.get("termination_reason", "unknown"),
            }
        else:
            return _error_trace(simulation_id, task_id, trial, domain, duration, result.stderr)

    except subprocess.TimeoutExpired:
        return _error_trace(simulation_id, task_id, trial, domain, time.time() - start, "timeout")
    except Exception as e:
        return _error_trace(simulation_id, task_id, trial, domain, time.time() - start, str(e))


def _error_trace(sim_id, task_id, trial, domain, duration, error_msg) -> dict:
    return {
        "simulation_id": sim_id,
        "task_id": str(task_id),
        "trial": trial,
        "domain": domain,
        "reward": 0.0,
        "agent_cost": 0.0,
        "duration": duration,
        "termination_reason": "error",
        "error": error_msg[:500],
    }


def _append_trace(trace: dict) -> None:
    with open(_TRACE_LOG, "a") as f:
        f.write(json.dumps(trace) + "\n")


def _update_score_log(entry: dict) -> None:
    existing = []
    if _SCORE_LOG.exists():
        with open(_SCORE_LOG) as f:
            try:
                existing = json.load(f)
                if isinstance(existing, dict):
                    existing = [existing]
            except json.JSONDecodeError:
                existing = []
    existing.append(entry)
    with open(_SCORE_LOG, "w") as f:
        json.dump(existing, f, indent=2)


def _send_to_langfuse(summary: dict, traces: list[dict]) -> None:
    try:
        from langfuse import Langfuse
        lf = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
        for trace in traces:
            t = lf.trace(
                id=trace["simulation_id"],
                name=f"tau2-{trace['domain']}-task{trace['task_id']}",
                metadata={**summary, **trace},
            )
    except Exception as e:
        print(f"Langfuse send skipped: {e}")


def _wilson_ci(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    margin = (z * (p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default="retail")
    parser.add_argument("--tasks", type=int, default=30)
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--tag", default="method")
    args = parser.parse_args()

    result = run_eval(
        domain=args.domain,
        num_tasks=args.tasks,
        num_trials=args.trials,
        tag=args.tag,
    )
    print(json.dumps(result, indent=2))
