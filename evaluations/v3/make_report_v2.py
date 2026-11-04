"""Derive build_report_v2.py from the previous round's report builder (string edits only)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
s = (ROOT / "build_comparison_report.py").read_text("utf-8")
start = s.index("LIMITS = [")
end = s.index("]\n", start) + 2
LIMITS = '''LIMITS = [
    "本次为新编的六个虚构人物、144组事实、24种考点与多种输入；与上轮题库无重叠。四个间隔复用同一事实，样本相关；考点或模态切片的题数不能相加。",
    "三路使用同一官方 DeepSeek-flash 作答及输出上限。千问只做嵌入和重排；RAG复用旧版实际输入观测及媒体回复，包含旧版感知错误，不是独立的视觉/语音系统。",
    "先冻结源码再编题；第一次启动后发现原文检索被情景接续挤占名额而中止并改码（见post-bank-code-revision.json），题库未改；全部1728份答案冻结后才打开判据。判卷隐藏版本标签，同模型自动判卷；Claude抽查不是独立人工判卷。",
    "题库和Core改动出自同一个助手（Claude），存在出题偏向改动的风险；考点沿用事实/改口/约定/边界等通用类别，判据在看到任何答案前冻结。",
    "主指标为576题整题通过率：required全部满足且无forbidden错误才算通过；终态执行失败留在分母。每个Core另做18项生命周期检查，不并入准确率。",
    "费用为保守估算加未结算预留，不是实际账单：DeepSeek按官方峰值费率乘1.5；千问按5元/百万token估算。",
    "没有真实等待半年，而是按冻结的逻辑时间重放180天对话。结论只适用于本轮配置和这套新题。",
]
'''
s = s[:start] + LIMITS + s[end:]
PAIRS = [
    ('== len(mapping) == 2088', '== len(mapping) == 1728'),
    ('r["persona"] == "N02" and r["delay_days"] == 15]', 'r["persona"] == "M02" and r["delay_days"] == 15]'),
    ('assert len(fixed) == 29', 'assert len(fixed) == 24'),
    ('"preregistered_N02_d15_all29"', '"preregistered_M02_d15_all24"'),
    ('("约定关系与线索", "时间与来源", "变化纠错与矛盾", "跨模态")',
     '("来源与归属", "时间与顺序", "变化纠错与矛盾", "跨模态", "计划假设与玩笑", "未知与隐私")'),
    ('同696题 · 6个虚构人物', '同576题 · 6个虚构人物'),
    ('}/696  {', '}/576  {'),
    ('执行失败旧版3题/新版7题，计入696分母。',
     '执行失败旧版{summary["overall"]["old"]["execution_failures"]}题/新版{summary["overall"]["new"]["execution_failures"]}题，计入576分母。'),
    ('Codex', 'Claude'),
    ('本轮新编696题', '本轮新编576题'),
    ('。2026-11-02"', '。2026-11-03"'),
    ('图像含空间图及日历', '图像含计数图和清点图'),
    ('/ 696 整题通过', '/ 576 整题通过'),
    ('r["persona"]=="N01" and r["delay_days"]==0', 'r["persona"]=="M01" and r["delay_days"]==0'),
    ('2026-11-02 · FROZEN COMPARISON', '2026-11-03 · FROZEN COMPARISON'),
    ('<h1>新题库，记忆优化带来了多少变化？</h1>', '<h1>第二轮记忆改进：新题库三路对照</h1>'),
    ('696题 × 旧版 / 新版 / 千问RAG。真实语音、空间图、日历、文件与对话；',
     '576题 × 旧版 / 新版 / 千问RAG。真实语音、计数图、文件表格、引用转发与对话；'),
    ('执行失败旧3题、新7题均保留在696分母。',
     '执行失败旧{summary["overall"]["old"]["execution_failures"]}题、新{summary["overall"]["new"]["execution_failures"]}题均保留在576分母。'),
    ('/ ¥50</strong>；含15次未结算预留',
     '/ ¥{ds["cap_cny"]}</strong>（另：旧题库冒烟¥0.39、中止的第一次启动¥5.57，三项合计不超过¥50）；含{ds["states"].get("UNKNOWN",0)}次未结算预留'),
    ('/ ¥30</strong>', '/ ¥{qw["cap_cny"]}</strong>'),
    ('<td>696（含失败', '<td>576（含失败'),
    ('<h2 id="questions">696题逐题核对</h2>', '<h2 id="questions">576题逐题核对</h2>'),
    ('全部29考点', '全部24考点'),
    ('696 / 696题', '576 / 576题'),
    ('finance("deepseek-usage.jsonl",50),"qwen":finance("qwen-usage.jsonl",30)',
     'finance("deepseek-usage.jsonl",44.04),"qwen":finance("qwen-usage.jsonl",50)'),
]
for old, new in PAIRS:
    assert old in s, old
    s = s.replace(old, new)
a = s.index('    sensitivity=summary["source_ambiguity_sensitivity"]')
b = s.index("<p><a href=\"review-selection.json\">", a)
s = s[:a] + '''    src=json.loads((ROOT/"source-freeze.json").read_text("utf-8"))
    doc+=f'<p>旧版提交{src["old_commit"][:8]}；新版{src["new_commit"][:8]}（分支 claude/memory-accuracy-v2）。Claude实际复核{summary["review_count"]}份回答（含预注册M02/d15全部24考点×三路72份），单独改判{summary["override_count"]}份；原自动标签保持不变。</p>''' + s[b:]
line = [x for x in s.splitlines(True) if 'summary["source_ambiguity_sensitivity"]' in x]
assert len(line) == 1
s = s.replace(line[0], "")
bad = [x for x in ("K23", "696", "2088", "N02", "N01") if x in s]
assert not bad, bad
(ROOT / "build_report_v2.py").write_text(s, "utf-8")
print("ok")
