"""Round-only offline analysis; frozen campaign code and inputs remain unchanged."""
import hashlib
import html
import importlib.util
import json
import os
import re
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
sys.path.insert(0, str(ROOT / ".deps"))
os.environ["MPLCONFIGDIR"] = str(ROOT / ".cache/matplotlib")
sys.argv = [__file__, "--round", str(ROOT)]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


P = module("frozen_campaign_report", WORKSPACE / "benchmarks/memory_campaign/report.py")
read, save, sha = P.read_rows, P.save, P.sha


def quantiles(values):
    return {"n": len(values), "median": statistics.median(values),
            "p95": statistics.quantiles(values, n=100, method="inclusive")[94],
            "max": max(values)} if values else {"n": 0}


def bootstrap(rows, cluster_field, repetitions=20000):
    import numpy as np
    groups = defaultdict(list)
    for r in rows:
        groups[r[cluster_field]].append(r)
    counts = np.array([len(v) for v in groups.values()], dtype=float)
    passed = np.array([[sum(r["arms"][a]["passed"] for r in v) for a in P.ARMS]
                       for v in groups.values()], dtype=float)
    rng = np.random.default_rng(20261103)
    indices = rng.integers(0, len(counts), size=(repetitions, len(counts)))
    rates = passed[indices].sum(axis=1) / counts[indices].sum(axis=1)[:, None]
    ci = lambda a: [float(v) for v in np.quantile(a, [.025, .975])]
    return {"cluster": cluster_field, "clusters": len(groups), "repetitions": repetitions,
            "seed": 20261103, "method": "paired percentile cluster bootstrap; question-weighted ratio",
            "accuracy_95_ci": {a: ci(rates[:, i]) for i, a in enumerate(P.ARMS)},
            "new_minus_old_points_95_ci": [v * 100 for v in ci((rates[:, 1] - rates[:, 0]))],
            "equal_cluster_weight_accuracy": {a: float((passed[:, i] / counts).mean())
                                               for i, a in enumerate(P.ARMS)},
            "exploratory_not_independent_story_or_persona_guarantee": True}


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
                  "Trace mapped to last completed native job immediately preceding each exam print, validated744 unique per arm.",
        "limitation": "Mixed serial/parallel schedule and CPU contention; descriptive only, not isolated performance attribution."})
    return out


def main():
    rows, grades = P.load()
    selected = P.prepare_review(rows, grades)
    reviewed = {r["key"] for r in read(P.GRADING / "review.jsonl")}
    assert {r["key"] for r in selected} <= reviewed
    uncertain = set()
    for vote in range(1, 4):
        for row in read(P.GRADING / f"vote-{vote}/grades.jsonl"):
            if row.get("anchor_failed") or row.get("judge_unresolved"):
                uncertain.add(row["key"])
    assert uncertain <= reviewed, len(uncertain - reviewed)
    for receipt in ("execution-freeze.json", "all-answers-frozen.json"):
        value = json.loads((ROOT / receipt).read_text("utf-8"))
        for name, digest in value.get("files_sha256", {}).items():
            assert sha(ROOT / name) == digest, (receipt, name)
    assert sha(ROOT / "anchors.jsonl") == "205a7f5f8547d3710e3e84d901e042475e44962406b0c7493fa624ab4dd79882"
    assert sha(P.GRADING / "grades.jsonl") == "92c2dbd37e3236b6c1e88f756b1c52d5e247387a03c736da06f246f44dd43329"
    original_limits = list(P.R.cfg["limitations"])
    limits = [x for x in original_limits if "原生新旧臂和人物串行" not in x]
    limits += [
        "实际调度：19:14旧版先开始；19:46:09起新旧臂并行，每臂人物串行。21:55起判卷，22:08:59起三票并行。混合调度且争用CPU，不能据整轮或单题耗时宣称隔离性能提升。",
        "细考点每个间隔通常只有6题（6个事实组），薄于参考图的10–19题；31个细类中的版本链视角共享6条链。168个事实组也共享6个人物及模板，区间为探索性描述。",
        "事后发现24道题有当前/当天时间指代歧义：主分数保留冻结判据，另对全部系统统一排除；9份钥匙归属答案存在语义边界，保留原多数票并给宽严范围。",
        "C12判据中的或原因不明，以及v3不因unsupported额外说法直接判错，会使部分错误采信后报颜色的回答过关；该类分数不能当作严格矛盾保留率。",
        "字段诊断为同一证据单元内的词串启发式，并非语义正确证据或端到端召回率；无法匹配的判据另列，不能把覆盖率称为准确率。",
        "提取时有一条引用即计提问时已抽取，不表示全部必要事实齐备；batch_failed是任务事件数，与坏JSON响应数定义不同。",
        "双供应商三票中的两票来自同一DeepSeek模型，三票不是三位独立人类；锚点来自已曝光v4复核材料，过门槛不保证每题判对。",
    ]
    P.R.cfg["limitations"] = limits
    summary = P.summarize(rows)
    summary["bootstrap"] = {"fact_group": bootstrap(rows, "dependency_group"),
                            "persona": bootstrap(rows, "persona")}
    summary["by_persona"] = {p: {a: P.score([r for r in rows if r["persona"] == p], a)
                                 for a in P.ARMS} for p in P.R.personas}
    audit = json.loads((ROOT / "question-validity-audit.json").read_text("utf-8"))
    excluded = {qid for f in audit["findings"] for qid in f["question_ids"]}
    kept = [r for r in rows if r["id"] not in excluded]
    summary["posthoc_validity_sensitivity"] = {"excluded_question_ids": sorted(excluded),
        "all_arms_uniform": True, "posthoc": True, "scores": {a: P.score(kept, a) for a in P.R.graded_arms},
        "new_minus_old_points": (P.score(kept, "new")["rate"] - P.score(kept, "old")["rate"]) * 100,
        "bootstrap": bootstrap(kept, "dependency_group")}
    boundaries = json.loads((P.GRADING / "review-semantic-boundaries.json").read_text("utf-8"))
    boundary_keys = {r["key"] for r in boundaries}
    bounds = {}
    for a in P.ARMS:
        certain = sum(r["arms"][a]["passed"] for r in rows if r["arms"][a]["key"] not in boundary_keys)
        n = sum(r["arms"][a]["key"] in boundary_keys for r in rows)
        bounds[a] = {"boundary_answers": n, "passed_min": certain, "passed_max": certain + n,
                     "rate_min": certain / len(rows), "rate_max": (certain + n) / len(rows)}
    summary["semantic_boundary_sensitivity"] = bounds
    summary["semantic_boundary_new_minus_old_points_range"] = [
        100 * (bounds["new"]["rate_min"] - bounds["old"]["rate_max"]),
        100 * (bounds["new"]["rate_max"] - bounds["old"]["rate_min"])]
    summary["content_tags_overlapping"] = {tag: {a: P.score([r for r in rows if tag in r["content_tags"]], a)
                                                 for a in P.ARMS}
        for tag in sorted({t for r in rows for t in r["content_tags"]})}
    smoke = P.finance(ROOT / "smoke/deepseek-usage.jsonl", 1)
    summary["finance"]["deepseek_smoke"] = smoke
    summary["finance"]["deepseek_combined"] = {
        "charged_or_held_cny": summary["finance"]["deepseek"]["charged_or_held_cny"] + smoke["charged_or_held_cny"],
        "cap_cny": 80, "invoice_verified": False}
    assert summary["finance"]["deepseek"]["charged_or_held_cny"] <= 79
    assert smoke["charged_or_held_cny"] <= 1
    assert summary["finance"]["deepseek_combined"]["charged_or_held_cny"] <= 80
    assert summary["finance"]["qwen"]["charged_or_held_cny"] <= 80
    assert all(g["passed"] for g in summary["judging"]["anchor_gates"].values())
    summary["native_metrics"] = native_metrics()
    for entry in summary.get("strata", {}).values():
        if "drop_z_shortest_vs_longest" in entry:
            entry["legacy_independent_item_z_NOT_USED_FOR_INFERENCE"] = entry.pop("drop_z_shortest_vs_longest")
    save(ROOT / "results.json", rows)
    save(ROOT / "summary.json", summary)
    overlay = {"at": datetime.now(UTC).isoformat(), "frozen_round_sha256": sha(ROOT / "round.json"),
               "frozen_report_sha256": sha(WORKSPACE / "benchmarks/memory_campaign/report.py"),
               "original_limitations": original_limits, "reporting_limitations": limits,
               "schedule_sources": ["schedule-amendment.json", "grading-schedule-amendment.json"],
               "inputs_unchanged": True, "review_complete": len(reviewed),
               "anchor_uncertain_reviewed": len(uncertain), "posthoc_audit": "question-validity-audit.json",
               "statistical_method": summary["bootstrap"],
               "matplotlib_docs": "https://matplotlib.org/stable/users/explain/figure/backends.html"}
    save(ROOT / "reporting-overlay.json", overlay)
    figures = P.charts(rows, summary)
    assert len(figures) > 0, "charts dependency missing"
    figures.insert(0, {"stem": "memory-summary", "title": "总体结果"})
    P.render(rows, summary, figures)
    diagnosis = module("frozen_campaign_diagnose", WORKSPACE / "benchmarks/memory_campaign/diagnose.py")
    diagnosis.main()
    summary["diagnosis"] = json.loads((ROOT / "evidence-diagnosis.json").read_text("utf-8"))["summary"]
    save(ROOT / "summary.json", summary)
    add_narrative(summary)
    print(json.dumps({"overall": summary["overall"], "paired": summary["paired_changes"],
                      "ci": summary["bootstrap"]["fact_group"]["new_minus_old_points_95_ci"],
                      "finance": {k: v["charged_or_held_cny"] for k, v in summary["finance"].items()},
                      "metrics": summary["native_metrics"]}, ensure_ascii=False))


def add_narrative(s):
    e = lambda v: html.escape(str(v), quote=True)
    def table(headers, rows):
        return '<table><thead><tr>' + ''.join(f'<th>{e(c)}</th>' for c in headers) + '</tr></thead><tbody>' + ''.join(
            '<tr>' + ''.join(f'<td>{e(c)}</td>' for c in row) + '</tr>' for row in rows) + '</tbody></table>'
    fmt = lambda v: f'{v:.1%}'
    ci = s["bootstrap"]["fact_group"]["new_minus_old_points_95_ci"]
    pci = s["bootstrap"]["persona"]["new_minus_old_points_95_ci"]
    points = s["new_minus_old_points"]
    content = '<section id="analysis"><h2>复核后的结论与证据</h2>'
    content += f'<p>同题配对新版较旧版{points:+.2f}个百分点；按168事实组重采样的探索性95%区间为{ci[0]:+.2f}到{ci[1]:+.2f}个百分点。'
    content += f'按6人物重采样为{pci[0]:+.2f}到{pci[1]:+.2f}个百分点。重复间隔和版本链视角没有作为独立样本；人物与模板依赖仍存在。</p>'
    content += table(['口径', '旧版', '新版', '千问RAG'], [
        ['冻结判据主结果'] + [f'{s["overall"][a]["passed"]}/744 ({fmt(s["overall"][a]["rate"])})' for a in P.ARMS],
        ['每事实组等权'] + [fmt(s['bootstrap']['fact_group']['equal_cluster_weight_accuracy'][a]) for a in P.ARMS],
        ['去除闭卷能答对的题'] + [f'{s["memory_dependent"][a]["passed"]}/{s["memory_dependent"][a]["total"]} ({fmt(s["memory_dependent"][a]["rate"])})' for a in P.ARMS],
        ['事后统一排除24道时间指代歧义题'] + [f'{s["posthoc_validity_sensitivity"]["scores"][a]["passed"]}/720 ({fmt(s["posthoc_validity_sensitivity"]["scores"][a]["rate"])})' for a in P.ARMS],
        ['9份语义边界答案宽严范围'] + [f'{fmt(s["semantic_boundary_sensitivity"][a]["rate_min"])}–{fmt(s["semantic_boundary_sensitivity"][a]["rate_max"])}' for a in P.ARMS],
    ])
    content += '<p>事后敏感性只帮助判断题库问题对结论的影响，不替换冻结主分数。C12的“或原因不明”判据及v3对额外无依据说法的处理较宽松，该分数不能解释为严格的冲突解决能力。</p>'
    all_rows = json.loads((ROOT / 'results.json').read_text('utf-8'))
    chain = [r for r in all_rows if r['group_id'].endswith('-C28')]
    other = [r for r in all_rows if not r['group_id'].endswith('-C28')]
    assert len(chain) == 96 and len(other) == 648
    s['chain_contribution'] = {'version_chain': {a: P.score(chain, a) for a in P.ARMS},
                               'other_questions': {a: P.score(other, a) for a in P.ARMS}}
    save(ROOT / 'summary.json', s)
    content += table(['提升的组成', '旧版', '新版', '千问RAG'], [
        [label] + [f'{P.score(rs,a)["passed"]}/{len(rs)} ({P.score(rs,a)["rate"]:.1%})' for a in P.ARMS]
        for label, rs in [('版本链：6事实组、96问', chain), ('其余162事实组、648问', other)]])
    content += '<p>总体净多答对38题，其中35题来自版本链。每事实组等权时旧版94.68%、新版96.43%，提升约1.75个百分点；题目加权的5.11个百分点不能解释为所有能力普遍改善。配对有65题改善、27题退步，应保留退步样本继续诊断；本轮不据答案修改冻结候选。</p>'
    content += '<p>本轮分层没有呈现链越长越差的单调趋势。每个链长只有1–2个事实组，链长与人物、转述干扰同时变化；不能用16或32个重复提问当作16或32条独立链来作显著性检验。原工具的独立题目z值仅保留在JSON的legacy字段，不作推断依据。</p>'
    category_changes = sorted(s['by_category'], key=lambda c: s['by_category'][c]['new']['rate'] - s['by_category'][c]['old']['rate'], reverse=True)
    content += '<h3>改进与仍失败的类型</h3>'
    content += table(['考点', '旧版', '新版', 'RAG', '新减旧'], [
        [next(r['category'] for r in P.R.questions if r['category_id'] == c)] +
        [f'{s["by_category"][c][a]["passed"]}/{s["by_category"][c][a]["total"]}' for a in P.ARMS] +
        [f'{100*(s["by_category"][c]["new"]["rate"]-s["by_category"][c]["old"]["rate"]):+.1f}pp']
        for c in category_changes])
    content += '<h3>真实记录中的成本与检索长尾</h3>'
    content += table(['指标', '旧版', '新版'], [
        ['提取调用数'] + [s['native_metrics'][a]['extraction_responses'] for a in ('old', 'new')],
        ['提取输入token'] + [s['native_metrics'][a]['usage_by_scenario']['memory_extract']['input_tokens'] for a in ('old', 'new')],
        ['提取输出token'] + [s['native_metrics'][a]['usage_by_scenario']['memory_extract']['output_tokens'] for a in ('old', 'new')],
        ['严格JSON解析失败响应（本地修复前）'] + [s['native_metrics'][a]['strict_json_parse_failures'] for a in ('old', 'new')],
        ['memory.batch_failed审计事件'] + [s['native_metrics'][a]['audit_actions'].get('memory.batch_failed', 0) for a in ('old', 'new')],
        ['memory.output_repaired审计事件'] + [s['native_metrics'][a]['audit_actions'].get('memory.output_repaired', 0) for a in ('old', 'new')],
        ['答题memory_recall调用'] + [s['native_metrics'][a]['exam_tool_calls'].get('memory_recall', 0) for a in ('old', 'new')],
        ['同题重复相同参数的memory_recall调用'] + [s['native_metrics'][a]['exam_memory_recall_duplicate_arguments'] for a in ('old', 'new')],
        ['有一次原文回查的题数'] + [s['native_metrics'][a]['exam_cases_with_raw_fallback'] for a in ('old', 'new')],
        ['收到STOPPED工具结果的题数'] + [s['native_metrics'][a]['exam_cases_with_stopped_tool_result'] for a in ('old', 'new')],
        ['进入首个模型调用前P50/P95秒'] + [f'{s["native_metrics"][a]["before_first_provider_seconds"]["median"]:.2f} / {s["native_metrics"][a]["before_first_provider_seconds"]["p95"]:.2f}' for a in ('old', 'new')],
        ['Core题目作业P50/P95秒'] + [f'{s["native_metrics"][a]["job_seconds"]["median"]:.2f} / {s["native_metrics"][a]["job_seconds"]["p95"]:.2f}' for a in ('old', 'new')],
    ])
    content += '<p>这些变化是整批修复的共同结果，没有隔离各项改动。耗时含混合串行/并行调度、CPU争用和网络波动，不能据此宣称单路速度提升。严格JSON失败数与批处理最终失败事件不是同一指标。</p>'
    content += table(['费用账本（估算及预留）', '人民币', '状态'], [
        ['DeepSeek主账', f'{s["finance"]["deepseek"]["charged_or_held_cny"]:.6f} / 79', s['finance']['deepseek']['states']],
        ['DeepSeek曝光冒烟', f'{s["finance"]["deepseek_smoke"]["charged_or_held_cny"]:.6f} / 1', s['finance']['deepseek_smoke']['states']],
        ['DeepSeek合计', f'{s["finance"]["deepseek_combined"]["charged_or_held_cny"]:.6f} / 80', '未读取正式账单'],
        ['千问独立账本', f'{s["finance"]["qwen"]["charged_or_held_cny"]:.6f} / 80', s['finance']['qwen']['states']],
    ])
    phases = s['finance']['deepseek']['phases']
    content += table(['本轮阶段费用（非发票）', 'DeepSeek', '千问', '合计人民币'], [
        ['旧版Core：重放、维护、答题', f'{phases["old"]["charged_or_held_cny"]:.4f}', '0', f'{phases["old"]["charged_or_held_cny"]:.4f}'],
        ['新版Core：重放、维护、答题', f'{phases["new"]["charged_or_held_cny"]:.4f}', '0', f'{phases["new"]["charged_or_held_cny"]:.4f}'],
        ['千问RAG检索+同DeepSeek生成器', f'{phases["rag"]["charged_or_held_cny"]:.4f}',
         f'{s["finance"]["qwen"]["phases"]["rag"]["charged_or_held_cny"]:.4f}',
         f'{phases["rag"]["charged_or_held_cny"]+s["finance"]["qwen"]["phases"]["rag"]["charged_or_held_cny"]:.4f}'],
        ['闭卷同生成器', f'{phases["closed"]["charged_or_held_cny"]:.4f}', '0', f'{phases["closed"]["charged_or_held_cny"]:.4f}'],
        ['三票含作废/重判的判卷', f'{phases["judge"]["charged_or_held_cny"]:.4f}',
         f'{s["finance"]["qwen"]["phases"]["judge"]["charged_or_held_cny"]:.4f}',
         f'{phases["judge"]["charged_or_held_cny"]+s["finance"]["qwen"]["phases"]["judge"]["charged_or_held_cny"]:.4f}'],
    ])
    content += '<p>新版Core阶段费用约7.53元，旧版约13.81元，下降45.5%；阶段包含同一历史的重放、维护与744题答题。RAG是千问向量/重排配DeepSeek回答，标签“千问RAG”不表示用千问回答；其阶段合计约19.41元。以上只覆盖本轮计量请求，未计本地CPU、存储及既有模型下载成本。</p>'
    content += '<h3>证据诊断</h3>'
    content += table(['启发式指标', '旧版', '新版', 'RAG'], [
        [label] + [fmt(s['diagnosis'][a][key]) if s['diagnosis'][a][key] is not None else '—' for a in P.ARMS]
        for key, label in [('sources_read_rate', '来源处理完成'), ('extraction_at_question_time', '提问时至少一条来源有提取引用'),
                           ('fields_in_prompt_rate', '可检查词串全进证据单元'), ('field_presence', '字段级词串覆盖')]])
    content += '<p>诊断排除问题本身、系统指令、ID和年份中的误匹配；按证据单元检查同现。仍不能保证语义正确、否定和时态被保留。未匹配字段也可能只是同义改写；完整原始表在evidence-diagnosis.json，不把该数值当作召回率或准确率。</p>'
    content += '<h3>判卷与调度核验</h3><p>全部2976份回答执行成功，答案冻结后再盲判。DeepSeek/DeepSeek/千问固定seed1/2/3，每批2锚点、最多2次重判；锚点门槛全部通过。449份复核、44份改判；包含预登记选择、争议/逐字核对及全部任一票锚点未决结果。复核由同一助手完成，非独立人工审计。</p>'
    content += '<p>第一票有效结果原样保留，其他两票并行。旧调度在独占边界退出属有意交接；汇总另遇Windows GBK日志读取错误，修复后用阻断HTTP的缓存聚合完成，新增供应商请求为0。原始错误、原始脚本、修复、4项合成检查及哈希证据均保留。</p>'
    content += '<p>阶段时间（北京时间）：旧版首启约19:14；并行切换19:46；新版21:32、旧版21:41完成；RAG21:49、闭卷21:54完成；三票22:38前完成、缓存聚合22:42完成。详细每题开始/结束、计费和调度修订均保留。</p>'
    content += '<h3>方法来源与可比范围</h3><p>优先参考<a href="https://github.com/Ornn8/memory-system-benchmark/tree/4c9d147ec650419cdd3e66d81d15582e4672fe3b">Ornn8固定版本</a>的半年逻辑时间、最近六轮、整题判定和多间隔设计；其次参考<a href="https://github.com/FuRongJun-1999/hive-memory-bench/tree/179b29451b7e528798569269560389e3863789d9">hive-memory-bench固定版本</a>的锚点、双判官、闭卷与依赖处理。正式714题卷未公开，本轮是新编744题，不是官方同卷成绩。</p>'
    content += '</section>'
    dsh = '<h2>dsh-memory 的看法</h2><p>本轮没有运行dsh-memory，不能从这份分数给它排位。作者截图反映该版本在其固定卷上的表现；本轮Core、千问RAG的数据和官方卷不相同，无法横向相减。值得继续借鉴其版本链、来源和闭卷/锚点检验；如要比较系统，需要同一公开卷、相同生成模型/历史窗口、相同预算及盲评规则重新测。</p>'
    path = ROOT / 'memory-report.html'
    text = path.read_text('utf-8')
    text = text.replace('<meta charset="utf-8">', '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">')
    text = text.replace('DeepSeek ¥38.30/¥79，千问 ¥33.10/¥80（保守估算）',
                        'DeepSeek主账 ¥38.30/¥79，另冒烟 ¥0.12/¥1（合计 ¥38.41/¥80）；千问 ¥33.10/¥80（保守估算）')
    text = text.replace('</style>', 'table{border-collapse:collapse;width:100%;margin:16px 0}th,td{text-align:left;border-bottom:1px solid #d1dce9;padding:9px;vertical-align:top}th{background:#eaf0fb}#analysis{margin:32px 0}p{line-height:1.75}.answers{grid-template-columns:repeat(2,minmax(0,1fr))}.answer{min-width:0;overflow-wrap:anywhere}@media(max-width:700px){main{padding:16px}.answers,.kpis{grid-template-columns:1fr}table{font-size:12px}}' + '</style>')
    text = text.replace('<h2>逐题</h2>', content + '<h2>逐题</h2>')
    text = text.replace('</main></html>', dsh + '</main></html>')
    path.write_text(text, 'utf-8')


if __name__ == '__main__':
    main()
