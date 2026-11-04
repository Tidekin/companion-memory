"""Aggregate immutable grades and separately logged Claude review into local report artifacts."""
import hashlib
import html
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from grade_blind import ROOT, read, save, sha, validate_coverage

ARMS = ("old", "new", "rag")
LABELS = {"old": "旧版 Core", "new": "新版 Core", "rag": "千问 RAG"}
COLORS = {"old": "#7D8798", "new": "#2859E8", "rag": "#008896"}
HATCH = {"old": "///", "new": "", "rag": ".."}
BANK = ROOT / "bank/suite-v1"
def configure_plot():
    # Same existing plot runtime as prior reports; aggregation/review needs no plotting dependency.
    global matplotlib, plt, np, Patch
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.font_manager import FontProperties
    from matplotlib.patches import Patch
    font = FontProperties(fname="LOCAL_PATH")
    plt.rcParams.update({"font.family": font.get_name(), "font.size": 11,
                         "axes.unicode_minus": False, "svg.fonttype": "path",
                         "figure.facecolor": "#F5F8FD", "axes.facecolor": "#F5F8FD"})
LIMITS = [
    "本次为新编的五个虚构人物、120组事实、24种考点与多种输入；与前两轮题库无重叠。四个间隔复用同一事实，样本相关；考点或模态切片的题数不能相加。",
    "三路使用同一官方 DeepSeek-flash 作答及输出上限。千问只做嵌入和重排；RAG复用旧版实际输入观测及媒体回复，包含旧版感知错误，不是独立的视觉/语音系统。",
    "先冻结源码再编题；冒烟只用已公开的第二轮题库；全部1440份答案冻结后才打开判据。判卷隐藏版本标签，同模型自动判卷；Claude抽查不是独立人工判卷。",
    "题库和Core改动出自同一个助手（Claude），存在出题偏向改动的风险；考点沿用事实/改口/约定/边界等通用类别，第三轮题目在看过第二轮诊断后编写，含更正类考点但措辞与结构全新；判据在看到任何答案前冻结。",
    "主指标为480题整题通过率：required全部满足且无forbidden错误才算通过；终态执行失败留在分母。每个Core另做18项生命周期检查，不并入准确率。",
    "费用为保守估算加未结算预留，不是实际账单：DeepSeek按官方峰值费率乘1.5；千问按5元/百万token估算。",
    "没有真实等待半年，而是按冻结的逻辑时间重放180天对话。结论只适用于本轮配置和这套新题。",
]


def load_data():
    freeze = json.loads((ROOT / "all-answers-frozen.json").read_text("utf-8"))
    for name, digest in freeze["files_sha256"].items():
        assert sha(ROOT / name) == digest, name
    questions = read(BANK / "questions.jsonl")
    answers = {a: [r for p in sorted((ROOT / "arms" / a / "results").glob("*/answers.jsonl")) for r in read(p)]
               for a in ("old", "new")}
    answers["rag"] = read(ROOT / "rag/answers.jsonl")
    validate_coverage(questions, answers)
    answer_maps = {a: {r["id"]: r for r in rows} for a, rows in answers.items()}
    mapping = read_json("grading/blind-mapping.json")
    grades = read(ROOT / "grading/grades.jsonl")
    assert len(grades) == len({r["key"] for r in grades}) == len(mapping) == 1440
    gmap = {r["key"]: r for r in grades}
    raw = {k: dict(v) for k, v in gmap.items()}
    mmap = {r["key"]: r for r in mapping}
    for m in mapping:
        assert m["answer_sha256"] == hashlib.sha256(answer_maps[m["arm"]][m["id"]].get("answer", "").encode()).hexdigest()
    overrides = read(ROOT / "grade-review-overrides.jsonl")
    assert len(overrides) == len({r["key"] for r in overrides})
    for r in overrides:
        assert r["original_grade"] == raw[r["key"]] and type(r["pass"]) is bool and r["reason"]
        gmap[r["key"]] = {**raw[r["key"]], "pass": r["pass"], "review_reason": r["reason"]}
    criteria = {r["id"]: r for r in read(BANK / "review-only/criteria.jsonl")}
    reverse = {(m["arm"], m["id"]): m for m in mapping}
    inputs = {r["id"]: r for p in (BANK / "inputs").glob("*.jsonl") for r in read(p)}
    rows = []
    for q in sorted(questions, key=lambda r: r["id"]):
        arms = {}
        for a in ARMS:
            ans, m = answer_maps[a][q["id"]], reverse[a, q["id"]]
            arms[a] = dict(key=m["key"], answer=ans.get("answer", ""), answer_sha256=m["answer_sha256"],
                           status=ans["status"], error=ans.get("error"), auto_grade=raw[m["key"]],
                           grade=gmap[m["key"]], passed=gmap[m["key"]]["pass"],
                           elapsed_seconds=latency(ans))
        op, npass = arms["old"]["passed"], arms["new"]["passed"]
        change = ("gain" if npass else "loss") if op != npass else ("both_pass" if op else "both_fail")
        rows.append({**q, "criteria": criteria[q["id"]], "arms": arms, "change": change,
                     "sources": [inputs[s] for s in q["source_ids"]]})
    return rows, mmap, raw


def read_json(name):
    return json.loads((ROOT / name).read_text("utf-8"))


def latency(answer):
    if "elapsed_seconds" in answer:
        return answer["elapsed_seconds"]
    if answer.get("actual_finished_at") and answer.get("actual_started_at"):
        return (datetime.fromisoformat(answer["actual_finished_at"])-datetime.fromisoformat(answer["actual_started_at"])).total_seconds()
    return None


def score(rows, arm):
    n = len(rows)
    passed = sum(r["arms"][arm]["passed"] for r in rows)
    failed = sum(r["arms"][arm]["status"] != "SUCCEEDED" for r in rows)
    return dict(passed=passed, total=n, rate=passed/n if n else None, execution_failures=failed)


def finance(name, cap):
    latest = {}
    for r in read(ROOT / name):
        latest.setdefault(r["id"], {}).update(r)
    assert latest and all(r["state"] in ("SETTLED", "UNKNOWN") for r in latest.values())
    total = sum(r["charged_or_held_cny"] for r in latest.values())
    assert total <= cap
    phases = defaultdict(lambda: dict(calls=0, charged_or_held_cny=0, input_tokens=0, cached_tokens=0, output_tokens=0))
    for r in latest.values():
        phase = r.get("phase", "unknown")
        label = (phase.split(":")[1] if phase.startswith("inference:") else phase)
        s, u = phases[label], r.get("usage", {})
        s["calls"] += 1
        s["charged_or_held_cny"] += r["charged_or_held_cny"]
        s["input_tokens"] += u.get("prompt_tokens", 0)
        s["cached_tokens"] += u.get("prompt_cache_hit_tokens", u.get("prompt_tokens_details", {}).get("cached_tokens", 0))
        s["output_tokens"] += u.get("completion_tokens", 0)
    return dict(charged_or_held_cny=total, cap_cny=cap, states=dict(Counter(r["state"] for r in latest.values())),
                unknown_held_cny=sum(r["charged_or_held_cny"] for r in latest.values() if r["state"] == "UNKNOWN"),
                phases=dict(phases), invoice_verified=False, previous_round_carry_cny=0)


def prepare_review(rows, mmap, raw):
    fixed = [r for r in rows if r["persona"] == "S02" and r["delay_days"] == 15]
    assert len(fixed) == 24
    selected = [(r, a, "preregistered_S02_d15_all24") for r in fixed for a in ARMS]
    # Deterministic supplemental samples: two changed questions per relevant family, all3arms.
    for family in ("来源与归属", "时间与顺序", "变化纠错与矛盾", "跨模态", "计划假设与梦", "未知与隐私"):
        pool = [r for r in rows if r["family"] == family
                and r["arms"]["old"]["auto_grade"]["pass"] != r["arms"]["new"]["auto_grade"]["pass"]]
        for r in pool[:2]:
            selected.extend((r, a, "supplement_" + family) for a in ARMS)
    byid = {r["id"]: r for r in rows}
    for key, grade in raw.items():
        if grade.get("index_annotation_errors") or grade.get("key_transcription_corrected"):
            m = mmap[key]
            selected.append((byid[m["id"]], m["arm"], "annotation_error"))
    out, seen = [], set()
    for r, arm, reason in selected:
        v = r["arms"][arm]
        if v["key"] in seen:
            continue
        seen.add(v["key"])
        out.append(dict(key=v["key"], arm=arm, id=r["id"], reason=reason,
                        answer_sha256=v["answer_sha256"], question=r["question"],
                        category=r["category"], required=r["criteria"]["required"], forbidden=r["criteria"]["forbidden"],
                        answer=v["answer"], auto_grade=raw[v["key"]]))
    if (ROOT / "review-selection.json").exists():
        assert json.loads((ROOT / "review-selection.json").read_text("utf-8")) == out
    else:
        save(ROOT / "review-selection.json", out)
    return out


def chart_save(fig, stem):
    fig.savefig(ROOT / (stem + ".png"), dpi=150, facecolor=fig.get_facecolor())
    fig.savefig(ROOT / (stem + ".svg"), facecolor=fig.get_facecolor())
    plt.close(fig)


def chart_header(fig, title, subtitle):
    height=fig.get_figheight()
    fig.text(.06, 1-.35/height, title, fontsize=23, weight="bold", color="#102F51", va="top")
    fig.text(.06, 1-.87/height, subtitle, fontsize=11, color="#53677E", va="top")
    fig.legend(handles=[Patch(facecolor=COLORS[a], hatch=HATCH[a], label=LABELS[a]) for a in ARMS],
               loc="upper left", bbox_to_anchor=(.055, 1-1.20/height), ncol=3, frameon=False)


def charts(rows, summary):
    configure_plot()
    fig, ax = plt.subplots(figsize=(11.6, 6.5))
    fig.subplots_adjust(left=.23, right=.89, bottom=.18, top=.74)
    chart_header(fig, "新题库 · 三路记忆测试", "同480题 · 5个虚构人物 · 同一官方DeepSeek作答 · 主指标为整题通过率")
    for i, a in enumerate(ARMS):
        s=summary["overall"][a]
        ax.barh(2-i, s["rate"]*100, color=COLORS[a], hatch=HATCH[a], height=.55)
        ax.text(s["rate"]*100+1, 2-i, f'{s["passed"]}/480  {s["rate"]:.1%}', va="center", weight="bold", color="#102F51")
    ax.set(yticks=[2,1,0], yticklabels=[LABELS[a] for a in ARMS], xlim=(0,100), xticks=[0,25,50,75,100])
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter())
    ax.grid(axis="x", alpha=.15);ax.set_axisbelow(True)
    for s in ax.spines.values():s.set_visible(False)
    fig.text(.06, .075, f'新版相对旧版 {summary["new_minus_old_percentage_points"]:+.2f} 个百分点；执行失败旧版{summary["overall"]["old"]["execution_failures"]}题/新版{summary["overall"]["new"]["execution_failures"]}题，计入480分母。\n每个Core独立生命周期检查18/18；自动判卷及Claude复核，非独立人工。', fontsize=10, color="#53677E")
    chart_save(fig, "memory-summary")
    families = list(dict.fromkeys(r["family"] for r in rows))
    chart_files = []
    for page, family in enumerate(families, 1):
        cats = list(dict.fromkeys(r["category_id"] for r in rows if r["family"] == family))
        fig, axes = plt.subplots(len(cats), 1, figsize=(12, 3.0+2.0*len(cats)), squeeze=False)
        fig.subplots_adjust(left=.28, right=.95, top=.82, bottom=.105, hspace=.62)
        if len(cats) <= 2:
            fig.subplots_adjust(top=1-1.90/fig.get_figheight(), bottom=1/fig.get_figheight())
        chart_header(fig, family, "柱高=整题通过率 · 柱顶=通过数/实际题数 · 每格三路各6题 · 统一0—100%轴")
        for ax, cid in zip(axes[:, 0], cats):
            subset=[r for r in rows if r["category_id"]==cid]
            title=subset[0]["category"]
            ax.text(-.32, .52, title, transform=ax.transAxes, ha="left", va="center", fontsize=12, weight="bold", color="#102F51", wrap=True)
            for j, a in enumerate(ARMS):
                s=[score([r for r in subset if r["delay_days"]==d],a) for d in (0,3,15,45)]
                xs=np.arange(4)+(j-1)*.21
                bars=ax.bar(xs, [v["rate"]*100 for v in s], width=.20,color=COLORS[a],hatch=HATCH[a])
                for b,v in zip(bars,s):
                    ax.text(b.get_x()+b.get_width()/2,b.get_height()+3,f'{v["passed"]}/{v["total"]}', ha="center",fontsize=9,color=COLORS[a],weight="bold",clip_on=False)
            ax.set(ylim=(0,100), yticks=[0,100], yticklabels=["0", "100%"], xticks=range(4), xticklabels=["当天","3天","15天","45天"])
            ax.grid(axis="y", alpha=.18);ax.set_axisbelow(True)
            for s in ax.spines.values():s.set_visible(False)
        fig.text(.06,.035,"重复事实的不同间隔相关；考点切片不得相加。终态执行失败计入分母。自动判卷+Claude复核，非独立人工。\n本轮新编480题；千问RAG复用旧版实际感知输出。2026-11-03",fontsize=10,color="#53677E")
        stem=f"category-{page:02d}"
        chart_save(fig,stem);chart_files.append(dict(stem=stem,title=family))
    groups = modality_groups(rows)
    fig,ax=plt.subplots(figsize=(12,7.5));fig.subplots_adjust(left=.26,right=.88,bottom=.16,top=.77)
    chart_header(fig,"按输入模态查看记忆表现","输入模态为源材料集合；含多种输入的题可进入多个切片，分母不可相加")
    for i,(label,subset) in enumerate(groups.items()):
        for j,a in enumerate(ARMS):
            v=score(subset,a);y=len(groups)-1-i+(1-j)*.23
            ax.barh(y,v["rate"]*100,height=.21,color=COLORS[a],hatch=HATCH[a])
            ax.text(v["rate"]*100+1,y,f'{v["passed"]}/{v["total"]}',fontsize=9,va="center",clip_on=False)
    ax.set(yticks=range(len(groups)),yticklabels=list(groups)[::-1],xlim=(0,100),xticks=[0,25,50,75,100]);ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter())
    ax.grid(axis="x",alpha=.15);ax.set_axisbelow(True)
    for s in ax.spines.values():s.set_visible(False)
    fig.text(.06,.06,"真实WAV经过ASR，错误保留；图像含价签图和清点图，文件含表格。RAG共享旧版感知输入。\n计入全部终态失败；自动判卷与Claude复核，非独立人工。",color="#53677E",fontsize=10)
    chart_save(fig,"modality-comparison")
    return chart_files


def modality_groups(rows):
    return {"纯文字源": [r for r in rows if set(r["input_modalities"]) == {"text"}],
            "含语音": [r for r in rows if "voice" in r["input_modalities"]],
            "含图像": [r for r in rows if "image" in r["input_modalities"]],
            "含文件/表格": [r for r in rows if "file" in r["input_modalities"]],
            "含引用/转发": [r for r in rows if set(r["input_modalities"]) & {"quote", "forward"}],
            "含助手历史": [r for r in rows if "assistant" in r["input_modalities"]]}


def render_html(rows, summary, figures):
    e=lambda s:html.escape(str(s),quote=True)
    cards="".join(f'<div class="kpi {a}"><span>{LABELS[a]}</span><strong>{summary["overall"][a]["rate"]:.1%}</strong><small>{summary["overall"][a]["passed"]} / 480 整题通过 · 执行失败 {summary["overall"][a]["execution_failures"]}</small></div>' for a in ARMS)
    figcards="".join(f'<figure><h3>{e(f["title"])}</h3><a href="{f["stem"]}.png"><img src="{f["stem"]}.png" loading="lazy" alt="{e(f["title"])}三路按四个间隔的分组柱状图"></a><figcaption><a href="{f["stem"]}.png">PNG</a> · <a href="{f["stem"]}.svg">SVG</a></figcaption></figure>' for f in figures)
    cats="".join(f'<option value="{e(r["category_id"])}">{e(r["category"])}</option>' for r in rows if r["persona"]=="S01" and r["delay_days"]==0)
    qcards=[]
    for r in rows:
        parts=[]
        for a in ARMS:
            v=r["arms"][a];label="通过" if v["passed"] else ("执行失败" if v["status"]!="SUCCEEDED" else "未通过")
            g=v["auto_grade"]
            misses=[r["criteria"]["required"][i] for i in g.get("missing",[]) if type(i)is int and 0<=i<len(r["criteria"]["required"])]
            violations=[r["criteria"]["forbidden"][i] for i in g.get("violations",[]) if type(i)is int and 0<=i<len(r["criteria"]["forbidden"])]
            review_notes={v["key"]:v["reason"] for v in read(ROOT/"assistant-grade-review.jsonl")}
            note=review_notes.get(v["key"], "")
            parts.append(f'<section class="answer {a}"><h4>{LABELS[a]} <b class="{"pass" if v["passed"] else "fail"}">{label}</b></h4><pre>{e(v["answer"] or v["error"] or "无可见回答")}</pre><small>状态：{e(v["status"])} · {v["elapsed_seconds"] or 0:.2f}秒</small><p class="annotation">自动标签：{"通过" if g["pass"] else "未通过"}<br>自动缺失：{e("；".join(misses) or "无有效索引")}<br>自动错误主张：{e("；".join(violations) or "无有效索引")}</p>{f"<p>Claude复核：{e(note)}</p>" if note else ""}</section>')
        sourceparts=[]
        for s in r["sources"]:
            asset=s.get("asset");media=""
            if asset:
                target="bank/suite-v1/"+asset
                assert (ROOT/target).is_file(),target
                media=f'<a class="attachment" href="{e(target)}">附件 {e(Path(asset).name)}</a>'
                if asset.endswith(".png"):media+=f'<img class="source-image" src="{e(target)}" loading="lazy" alt="{e(s["id"])}原始空间或日历图片">'
                if asset.endswith(".wav"):media+=f'<audio controls preload="none" src="{e(target)}"></audio>'
            sourceparts.append(f'<p><b>{e(s["id"])} · {e(s["now"])}</b><br>{e(s.get("text") or s.get("caption") or "媒体原件")}<br>{media}</p>')
        search=" ".join([r["id"],r["question"],r["category"]]+[r["arms"][a]["answer"] for a in ARMS]).lower()
        qcards.append(f'<details class="question" data-category="{r["category_id"]}" data-delay="{r["delay_days"]}" data-modal="{e(" ".join(r["input_modalities"]))}" data-change="{r["change"]}" data-search="{e(search)}"><summary><code>{r["id"]}</code> {e(r["category"])} · {r["delay_days"]}天 <span>{" / ".join("✓" if r["arms"][a]["passed"] else "×" for a in ARMS)}（旧/新/RAG）</span></summary><h3>{e(r["question"])}</h3><div class="answers">{"".join(parts)}</div><details><summary>冻结判据与来源附件</summary><p>必须满足：{e("；".join(r["criteria"]["required"]))}</p><p>禁止的错误主张：{e("；".join(r["criteria"]["forbidden"]))}</p>{"".join(sourceparts)}</details></details>')
    ds,qw=summary["finance"]["deepseek"],summary["finance"]["qwen"]
    doc='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Companion Core 新题库三路记忆测试</title><style>
    :root{color-scheme:light;font-family:"Microsoft YaHei",sans-serif;color:#17334f;background:#f5f8fd}*{box-sizing:border-box}body{margin:0}main{max-width:1260px;margin:auto;padding:48px 34px}header{border-top:6px solid #2859e8;padding-top:24px}h1{font-size:34px;letter-spacing:-1px;margin:0 0 14px}p{line-height:1.75}small,.muted{color:#586c81}.eyebrow{font-size:12px;letter-spacing:2px;color:#546a85}.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin:28px 0}.kpi{padding:22px;background:#fff;border-top:4px solid #7d8798}.kpi.new{border-color:#2859e8}.kpi.rag{border-color:#008896}.kpi span,.kpi small{display:block}.kpi strong{display:block;font-size:42px;margin:8px 0}.callout{padding:18px 22px;background:#e7eefb;border-left:4px solid #2859e8}a{color:#214fbc}nav{display:flex;gap:24px;margin:24px 0;flex-wrap:wrap}figure{margin:28px 0;padding:18px;background:white}figure img{display:block;width:100%;height:auto}figcaption{padding-top:8px;color:#586c81}h2{margin-top:50px;font-size:26px}.controls{position:sticky;top:0;background:#eef3fa;padding:12px 0;z-index:3;display:flex;flex-wrap:wrap;gap:8px}input,select{border:1px solid #a6b8ca;background:#fff;padding:10px;font:inherit;border-radius:4px}input{flex:1;min-width:180px}select{max-width:260px}.question{border-bottom:1px solid #d1dce9;padding:16px 0}.question>summary{cursor:pointer;line-height:1.8}.question>summary span{float:right;font-size:12px}.answers{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.answer{border-top:4px solid #7d8798;background:#fff;padding:14px;overflow-wrap:anywhere}.answer.new{border-color:#2859e8}.answer.rag{border-color:#008896}h4{margin:4px 0 14px}.pass{color:#087869}.fail{color:#a43d40}pre{font:inherit;white-space:pre-wrap;line-height:1.8}.annotation{font-size:12px;color:#586c81}.source-image{display:block;max-width:100%;width:600px;margin:15px 0}audio{display:block;width:min(100%,520px);margin-top:10px}table{border-collapse:collapse;width:100%;background:white}td,th{text-align:left;border-bottom:1px solid #d1dce9;padding:12px}code{font-size:12px}.foot{margin-top:40px;border-top:1px solid #d1dce9;padding-top:20px}.question[hidden]{display:none}@media(max-width:700px){main{padding:24px 16px}h1{font-size:27px}.kpis{grid-template-columns:1fr}.answers{grid-template-columns:1fr}.question>summary span{float:none;display:block}.controls{position:static}input,select{width:100%;max-width:none}figure{padding:0;margin:20px -6px}.kpi strong{font-size:34px}}@media print{.controls,nav{display:none}.question{break-inside:avoid}}
    @media(max-width:700px){figure{overflow-x:auto}figure img{min-width:900px}}</style><main><header><div class="eyebrow">COMPANION CORE · 2026-11-03 · FROZEN COMPARISON</div><h1>第三轮记忆改进：新题库三路对照</h1><p class="muted">480题 × 旧版 / 新版 / 千问RAG。真实语音、价签图、文件表格、引用转发与对话；同一官方DeepSeek模型作答。</p></header>'''
    doc+=f'<div class="kpis">{cards}</div><p class="callout">新版较旧版 <strong>{summary["new_minus_old_percentage_points"]:+.2f} 个百分点</strong>。配对比较：新版独有通过{summary["paired_changes"]["gain"]}题；旧版独有通过{summary["paired_changes"]["loss"]}题。执行失败旧{summary["overall"]["old"]["execution_failures"]}题、新{summary["overall"]["new"]["execution_failures"]}题均保留在480分母。独立生命周期旧/新各18/18。</p>'
    doc+='<nav><a href="#categories">考点柱状图</a><a href="#modalities">输入模态</a><a href="#questions">逐题核对</a><a href="#method">方法与局限</a><a href="results.json">逐题JSON</a><a href="summary.json">汇总JSON</a></nav>'
    doc+='<h2 id="categories">具体考点 × 提问间隔</h2><p>每格旧版、新版、千问RAG三根柱，统一0–100%比例，柱顶为通过数/实际题数。每个间隔同6人物；重复考点和同一事实不能相加。窄屏可横向滚动图表，或打开PNG查看。</p>'+figcards
    doc+='<h2 id="modalities">输入模态</h2><figure><a href="modality-comparison.png"><img src="modality-comparison.png" loading="lazy" alt="六类输入模态整题通过率"></a><figcaption><a href="modality-comparison.svg">SVG</a> · 重叠切片不可相加</figcaption></figure>'
    doc+=f'<h2>费用与执行</h2><p>本轮DeepSeek <strong>¥{ds["charged_or_held_cny"]:.4f} / ¥{ds["cap_cny"]}</strong>（另：冒烟¥0.26，合计不超过¥50）；含{ds["states"].get("UNKNOWN",0)}次未结算预留¥{ds["unknown_held_cny"]:.4f}。千问 <strong>¥{qw["charged_or_held_cny"]:.4f} / ¥{qw["cap_cny"]}</strong>。两者均为保守估算，非账单；未将native内部账重复相加，未继承上轮成本。</p><table><tr><th>路别</th><th>终态答题</th><th>答题耗时中位数 / P95</th><th>生命周期</th></tr>'+''.join(f'<tr><td>{LABELS[a]}</td><td>480（含失败{summary["overall"][a]["execution_failures"]}）</td><td>{summary["latency"][a]["median_seconds"]:.2f}s / {summary["latency"][a]["p95_seconds"]:.2f}s</td><td>{"18/18" if a!="rag" else "不适用"}</td></tr>' for a in ARMS)+'</table><p class="muted">耗时为每题实际入口到终态（RAG从检索后生成计时），含并发、工具或失败等待；不代表纯模型速度。</p>'
    doc+='<h2 id="questions">480题逐题核对</h2><p>展开可见三路原始回答、自动标签、独立记录的改判，以及冻结判据和源附件。搜索同时覆盖题目与三路回答。</p><div class="controls"><input id="search" aria-label="搜索题号题目与回答" placeholder="搜索题号、题目或回答…"><select id="category" aria-label="考点"><option value="">全部24考点</option>'+cats+'</select><select id="delay" aria-label="间隔"><option value="">全部间隔</option><option value="0">当天</option><option value="3">3天</option><option value="15">15天</option><option value="45">45天</option></select><select id="modality" aria-label="输入模态"><option value="">全部模态</option>'+''.join(f'<option value="{m}">{l}</option>' for m,l in [('text','文字'),('voice','语音'),('image','图像'),('file','文件'),('quote','引用'),('forward','转发'),('assistant','助手历史')])+'</select><select id="change" aria-label="旧新变化"><option value="">全部旧新变化</option><option value="gain">新版独有通过</option><option value="loss">旧版独有通过</option><option value="both_pass">两版均通过</option><option value="both_fail">两版均未通过</option></select></div><p id="count" aria-live="polite">480 / 480题</p>'+''.join(qcards)
    doc+='<h2 id="method">方法、证据和局限</h2>'+''.join(f'<p>{e(v)}</p>' for v in LIMITS)
    src=json.loads((ROOT/"source-freeze.json").read_text("utf-8"))
    doc+=f'<p>旧版提交{src["old_commit"][:8]}；新版{src["new_commit"][:8]}（分支 claude/memory-accuracy-v2）。Claude实际复核{summary["review_count"]}份回答（含预注册S02/d15全部24考点×三路72份），单独改判{summary["override_count"]}份；原自动标签保持不变。</p><p><a href="review-selection.json">复核选择</a> · <a href="assistant-grade-review.jsonl">Claude复核记录</a> · <a href="grade-review-overrides.jsonl">改判记录</a> · <a href="coverage-and-freeze.json">覆盖与哈希核对</a> · <a href="grading/grades.jsonl">原自动标签</a> · <a href="all-answers-frozen.json">原始答案冻结</a></p><footer class="foot muted">本地报告 · 无外部资源加载 · 结果由冻结原始证据汇总 · 非独立人工评测</footer></main>'
    doc+='''<script>const qs=[...document.querySelectorAll('.question')];const ids=['search','category','delay','modality','change'];function applyFilters(){const v=Object.fromEntries(ids.map(id=>[id,document.getElementById(id).value.trim().toLowerCase()]));let n=0;for(const q of qs){const ok=(!v.search||q.dataset.search.includes(v.search))&&(!v.category||q.dataset.category.toLowerCase()===v.category)&&(!v.delay||q.dataset.delay===v.delay)&&(!v.modality||q.dataset.modal.split(' ').includes(v.modality))&&(!v.change||q.dataset.change===v.change);q.hidden=!ok;if(ok)n++;}document.getElementById('count').textContent=n+' / '+qs.length+'题';return n;}ids.forEach(id=>document.getElementById(id).addEventListener(id==='search'?'input':'change',applyFilters));window.applyFilters=applyFilters;</script></html>'''
    (ROOT / "memory-report.html").write_text(doc,"utf-8")


def main():
    rows,mmap,raw=load_data()
    selection=prepare_review(rows,mmap,raw)
    if "--prepare-review" in sys.argv:
        print("review_selection",len(selection));return
    reviews=read(ROOT/"assistant-grade-review.jsonl")
    reviewed={r["key"]:r for r in reviews}
    assert len(reviews)==len(reviewed) and {r["key"] for r in selection} <= set(reviewed)
    for key,r in reviewed.items():
        assert r["reviewer"]=="Claude" and r["reason"] and type(r["review_pass"])is bool
        assert r["answer_sha256"]==mmap[key]["answer_sha256"] and r["auto_pass"]==raw[key]["pass"]
        actual = next(q["arms"][mmap[key]["arm"]]["passed"] for q in rows if q["id"]==mmap[key]["id"])
        assert actual == r["review_pass"], "Changed review must have a separate matching override"
    assert all(not g.get("index_annotation_errors") or k in reviewed for k,g in raw.items())
    summary=dict(status="REVIEWED_AWAITING_VISUAL_QA",at=datetime.now(UTC).isoformat(),
                 overall={a:score(rows,a) for a in ARMS},paired_changes=dict(Counter(r["change"] for r in rows)),
                 finance={"deepseek":finance("deepseek-usage.jsonl",49),"qwen":finance("qwen-usage.jsonl",50)},
                 review_count=len(reviews),override_count=len(read(ROOT/"grade-review-overrides.jsonl")),
                 not_independent_human=True,limitations=LIMITS)
    summary["new_minus_old_percentage_points"]=(summary["overall"]["new"]["rate"]-summary["overall"]["old"]["rate"])*100
    summary["latency"]={a:dict(median_seconds=statistics.median(v),p95_seconds=statistics.quantiles(v,n=100,method="inclusive")[94],n=len(v)) for a in ARMS if (v:=[r["arms"][a]["elapsed_seconds"] for r in rows if r["arms"][a]["elapsed_seconds"] is not None])}
    summary["modality"]={m:{a:score(rs,a) for a in ARMS} for m,rs in modality_groups(rows).items()}
    summary["category_delay"]={cid:{str(d):{a:score([r for r in rows if r["category_id"]==cid and r["delay_days"]==d],a) for a in ARMS} for d in (0,3,15,45)} for cid in sorted({r["category_id"] for r in rows})}
    save(ROOT/"results.json",rows);save(ROOT/"summary.json",summary)
    figures=charts(rows,summary);render_html(rows,summary,figures)
    save(ROOT/"report-build.json",dict(figures=figures,results_sha256=sha(ROOT/"results.json"),summary_sha256=sha(ROOT/"summary.json"),html_sha256=sha(ROOT/"memory-report.html")))
    print(json.dumps(summary["overall"],ensure_ascii=False))


if __name__=="__main__":main()
