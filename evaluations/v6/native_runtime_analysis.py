"""Offline native runtime analysis reused from v5; never executes the v5 writer."""
import importlib.util
import json
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parents[1]
sys.argv=[__file__, '--round', str(ROOT)]
spec=importlib.util.spec_from_file_location('v6_runtime_report',WORKSPACE/'benchmarks/memory_campaign/report.py')
P=importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)
read,save=P.read_rows,P.save

def quantiles(values):
    return {"n": len(values), "median": statistics.median(values),
            "p95": statistics.quantiles(values, n=100, method="inclusive")[94],
            "max": max(values)} if values else {"n": 0}

def native_metrics():
    out = {}
    detail = []
    for arm in ("old", "new"):
        usage, audit, rejected = defaultdict(Counter), Counter(), Counter()
        request_count = extraction_count = bad_json = no_content = 0
        tools, duplicates, raw_fallback_cases, stopped_cases = Counter(), 0, set(), set()
        per_case = defaultdict(Counter)
        for directory in sorted((P.R.arm_dir(arm) / "results").iterdir()):
            if not directory.is_dir():
                continue
            db = sqlite3.connect(f"file:{directory / 'core.sqlite3'}?mode=ro", uri=True)
            db.row_factory = sqlite3.Row
            for row in db.execute("SELECT scenario, input_tokens, cached_input_tokens, output_tokens, state "
                                  "FROM model_usage"):
                entry = usage[row["scenario"]]
                entry.update(calls=1, input_tokens=row["input_tokens"] or 0,
                             cached_input_tokens=row["cached_input_tokens"] or 0,
                             output_tokens=row["output_tokens"] or 0)
                entry["state_" + row["state"]] += 1
            for row in db.execute("SELECT action,safe_detail_json FROM audit_log WHERE action LIKE 'memory.%'"):
                audit[row["action"]] += 1
                if row["action"] == "memory.candidate_rejected":
                    value = json.loads(row["safe_detail_json"] or "{}")
                    rejected[str(value.get("reason", "UNSPECIFIED"))] += 1
            db.close()
            requests, responses = read(directory / "requests.jsonl"), read(directory / "responses.jsonl")
            assert len(requests) == len(responses), (arm, directory.name, "unclosed request")
            seen = defaultdict(set)
            for request, response in zip(requests, responses, strict=True):
                assert request.get("case") == response.get("case")
                assert request.get("phase") == response.get("phase")
                request_count += 1
                choices = response.get("response", {}).get("choices", [])
                if 'episode_summaries' in json.dumps(request["payload"], ensure_ascii=False):
                    extraction_count += 1
                    content = choices[0].get("message", {}).get("content") if choices else None
                    if not content:
                        no_content += 1
                    else:
                        try:
                            json.loads(content)
                        except (ValueError, TypeError):
                            bad_json += 1
                if request.get("phase") != "exam":
                    continue
                case = request["case"]
                for message in request["payload"].get("messages", []):
                    if message.get("role") != "tool":
                        continue
                    value = str(message.get("content", ""))
                    if '"raw_turns"' in value:
                        raw_fallback_cases.add(case)
                    if '"STOPPED"' in value:
                        stopped_cases.add(case)
                for choice in choices:
                    for call in choice.get("message", {}).get("tool_calls", []):
                        function = call.get("function", {})
                        name = function.get("name", "UNKNOWN")
                        tools[name] += 1
                        per_case[case][name] += 1
                        if name != "memory_recall":
                            continue
                        arg = function.get("arguments", "")
                        try:
                            arg = json.dumps(json.loads(arg), sort_keys=True, ensure_ascii=False)
                        except (ValueError, TypeError):
                            pass
                        if arg in seen[case]:
                            duplicates += 1
                        seen[case].add(arg)
        stages = defaultdict(dict)
        last_done = None
        latency_rows = []
        for line in (P.R.arm_dir(arm) / "inference.log").read_text("utf-8", errors="replace").splitlines():
            if line.startswith("{"):
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                trace = (row.get("session"), row.get("trace_id"))
                if not trace[1]:
                    continue
                stage = row.get("stage")
                if stage in {"t_job_started", "t_context_ready", "t_model_request", "t_job_done"}:
                    stages[trace].setdefault(stage, row)
                if stage == "t_job_done":
                    last_done = trace
            elif line.startswith("exam "):
                case = line.split()[1]
                assert last_done and last_done in stages, (arm, case)
                s = stages[last_done]
                assert {"t_job_started", "t_model_request", "t_job_done"} <= s.keys()
                value = {"arm": arm, "id": case, "session": last_done[0], "trace_id": last_done[1],
                         "before_first_provider_seconds": (s["t_model_request"]["monotonic_ns"]
                              - s["t_job_started"]["monotonic_ns"]) / 1e9,
                         "job_seconds": (s["t_job_done"]["monotonic_ns"]
                              - s["t_job_started"]["monotonic_ns"]) / 1e9}
                latency_rows.append(value)
                last_done = None
        assert len(latency_rows) == len({r["id"] for r in latency_rows}) == P.R.total
        assert len({(r["session"], r["trace_id"]) for r in latency_rows}) == P.R.total
        answers = {r["id"]: r for r in P.R.arm_answers(arm)}
        # Native answer elapsed_seconds includes only the SDK exam interval; compare monotonic totals.
        for row in latency_rows:
            full = P.latency(answers[row["id"]])
            assert row["job_seconds"] <= full + 1, (row["id"], row["job_seconds"], full)
        assert extraction_count == usage['memory_extract']['calls'], (arm, extraction_count, usage)
        out[arm] = {"request_response_pairs": request_count, "usage_by_scenario": dict(usage),
                    "audit_actions": dict(audit), "rejection_reason_codes": dict(rejected),
                    "extraction_responses": extraction_count, "strict_json_parse_failures": bad_json,
                    "extraction_without_content": no_content, "exam_tool_calls": dict(tools),
                    "exam_memory_recall_duplicate_arguments": duplicates,
                    "exam_cases_with_raw_fallback": len(raw_fallback_cases),
                    "exam_cases_with_stopped_tool_result": len(stopped_cases),
                    "exam_recall_calls_distribution": quantiles(
                        [per_case[q["id"]]["memory_recall"] for q in P.R.questions]),
                    "before_first_provider_seconds": quantiles(
                        [r["before_first_provider_seconds"] for r in latency_rows]),
                    "job_seconds": quantiles([r["job_seconds"] for r in latency_rows])}
        detail.extend(latency_rows)
    save(ROOT / "native-runtime-metrics.json", {"summary": out, "exam_traces": detail,
        "method": "Read-only closed DBs; request/response phase+case-aligned pairs; emitted tool calls only. "
                  "Extraction classified by episode_summaries protocol. Strict JSON failures do not equal failed batches. "
                  "Trace mapped to last completed native job immediately preceding each exam print, validated792 unique per arm.",
        "limitation": "Parallel two-arm schedule and CPU contention; descriptive only, not isolated performance attribution."})
    return out

if __name__ == "__main__":
    native_metrics()
