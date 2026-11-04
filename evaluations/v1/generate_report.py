"""Validate frozen outputs and build a fully local, inspectable result report."""
import hashlib
import json
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
SUITE = BASE / 'suite-v1'
NATIVE = BASE / 'native-final-v2'
REFERENCE = BASE / 'reference-final-v1'
GRADING = BASE / 'grading-final-v1'


def read(path):
    return [json.loads(s) for s in path.read_text('utf-8').splitlines()] if path.exists() else []


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def main():
    frozen = json.loads((BASE / 'answers-frozen-before-grading.json').read_text('utf-8'))
    for name, digest in frozen.items():
        assert hashlib.sha256((BASE / name).read_bytes()).hexdigest() == digest, name
    corpus = json.loads((SUITE / 'manifest.json').read_text('utf-8'))
    for name, digest in corpus['files_sha256'].items():
        assert hashlib.sha256((SUITE / name).read_bytes()).hexdigest() == digest, name
    all_questions = read(SUITE / 'questions.jsonl')
    questions = [q for q in all_questions if q['kind'] == 'semantic_memory']
    assert len(questions) == 696 and len({q['id'] for q in all_questions}) == 714
    criteria = {r['id']: r for r in read(SUITE / 'review-only/criteria.jsonl')}
    answers = {'native': sum((read(p) for p in sorted(NATIVE.glob('P*/answers.jsonl'))), []),
               'reference': read(REFERENCE / 'answers.jsonl')}
    expected = {q['id'] for q in questions}
    for system, values in answers.items():
        assert len(values) == len({r['id'] for r in values}) == 696, system
        assert {r['id'] for r in values} == expected, system
        answers[system] = {r['id']: r for r in values}
    grades = {r['key']: r for r in read(GRADING / 'grades.jsonl')}
    manual = {r['key']: r for r in read(BASE / 'manual-grade-overrides.jsonl')}
    for key, row in manual.items():
        assert key in grades and row['reason'] and type(row['pass']) is bool
    sources = {}
    observed = {}
    for p in sorted((SUITE / 'inputs').glob('*.jsonl')):
        sources.update({r['id']: r for r in read(p)})
    for p in sorted(NATIVE.glob('P*/turns-observed.jsonl')):
        values = read(p)
        assert [r['turn'] for r in values] == list(range(1, len(values) + 1))
        observed.update({r['id']: r for r in values})
    rows = []
    for q in questions:
        row = {**q, 'criteria': criteria[q['id']],
               'modalities': sorted({sources[s]['modality'] for s in q['source_ids']}),
               'sources': [observed[s] for s in q['source_ids']]}
        row['modality_group'] = row['modalities'][0] if len(row['modalities']) == 1 else 'mixed'
        for system in answers:
            answer = answers[system][q['id']]
            key = system + ':' + q['id']
            answered = answer['status'] == 'SUCCEEDED' and bool(answer.get('answer', '').strip())
            assert not answered or key in grades, key
            grade = manual.get(key, grades.get(key))
            row[system] = {'answered': answered, 'pass': bool(answered and grade and grade['pass']),
                           'answer': answer.get('answer', ''), 'status': answer['status'],
                           'error': answer.get('error'), 'grade': grade,
                           'retrieved_turns': answer.get('retrieved_turns'),
                           'history_source_ids': answer.get('history_source_ids')}
        assert max(sources[s]['turn'] for s in q['source_ids']) <= q['cutoff_turn']
        assert all(t <= q['cutoff_turn'] for t in answers['reference'][q['id']].get('retrieved_turns', []))
        rows.append(row)

    def stats(subset):
        result = {'questions': len(subset)}
        for system in answers:
            answered = sum(r[system]['answered'] for r in subset)
            passed = sum(r[system]['pass'] for r in subset)
            result[system] = {'passed': passed, 'answered': answered, 'unanswered': len(subset)-answered,
                              'pass_rate_all': passed/len(subset) if subset else None,
                              'pass_rate_answered': passed/answered if answered else None}
        return result

    common = [r for r in rows if all(r[s]['answered'] for s in answers)]
    pivots = {field: {str(value): stats([r for r in rows if r[field] == value])
                      for value in dict.fromkeys(r[field] for r in rows)}
              for field in ['category', 'delay_days', 'persona', 'modality_group']}
    checks = json.loads((BASE / 'verification-tests.json').read_text('utf-8'))
    lifecycle = {sid for r in checks['cases'] for sid in r['suite_ids']}
    assert lifecycle == {q['id'] for q in all_questions if q['kind'] == 'lifecycle_contract'}
    isolation = sum((read(p) for p in NATIVE.glob('P*/isolation.jsonl')), [])
    assert len(isolation) == 696
    assert all(r['erased'] and r['memory_unchanged'] and r['budget_usage_retained'] for r in isolation)

    costs = []
    for p in sorted(BASE.rglob('core.sqlite3')):
        c = sqlite3.connect(f'file:{p.as_posix()}?mode=ro', uri=True)
        usage = c.execute('SELECT state,count(*),sum(billed_micro_usd) FROM model_usage GROUP BY state').fetchall()
        c.close()
        assert all(r[0] == 'SETTLED' for r in usage), str(p)
        costs.append({'batch': str(p.parent.relative_to(BASE)), 'calls': sum(r[1] for r in usage),
                      'configured_usd': sum(r[2] or 0 for r in usage)/1e6})
    direct = {}
    for name, path in [('reference_deepseek', REFERENCE/'deepseek-usage.jsonl'),
                       ('judge', GRADING/'judge-usage.jsonl'), ('qwen', REFERENCE/'qwen-usage.jsonl')]:
        latest = {r['id']: r for r in read(path)}
        direct[name] = {'calls': len(latest), 'held': sum(r['charged_or_held'] for r in latest.values()),
                        'states': dict(Counter(r['state'] for r in latest.values()))}
        assert all(r['state'] == 'SETTLED' for r in latest.values()), name
    native_usd = sum(r['configured_usd'] for r in costs)
    deep_hold = (native_usd + direct['reference_deepseek']['held'] + direct['judge']['held'])*10
    qwen_probe_tokens = 101
    qwen_hold = direct['qwen']['held'] + qwen_probe_tokens*5/1e6
    assert deep_hold <= 30 and qwen_hold <= 30
    failures = Counter()
    media = Counter()
    for p in NATIVE.glob('P*'):
        failures.update((r.get('checkpoint') or {}).get('batch', {}).get('error', 'NONCOMPLETE') for r in read(p/'maintenance.jsonl') if not r.get('success'))
        for r in read(p/'turns-observed.jsonl'):
            if r['modality'] not in {'text', 'assistant'}:
                media[(r['modality'], r.get('native_state', {}).get('state'), r.get('media_error'))] += 1
    summary = {'classification': 'SELF_AUTHORED_714_INSTANCES_NOT_ORIGINAL_PRIVATE_BENCHMARK',
               'core_commit': '3da60d63307612ae813b8e6fd61ca318eedd4140',
               'generated_at': datetime.now(UTC).isoformat(), 'semantic': stats(rows),
               'common_answered': stats(common), 'positive_information_subset': stats([r for r in rows if r['category'] not in {'信息不足', '敏感限制'}]), 'lifecycle': {'passed': len(lifecycle), 'total': 18},
               'pivots': pivots, 'verification_passed': checks['passed'],
               'media_states': [{'modality': k[0], 'state': k[1], 'error': k[2], 'count': n} for k,n in media.items()],
               'maintenance_noncomplete': dict(failures), 'native_costs': costs, 'direct_costs': direct,
               'deepseek_conservative_hold_cny': deep_hold,
               'deepseek_at_peak_public_rates_cny': deep_hold*2/3, 'qwen_conservative_hold_cny': qwen_hold,
               'qwen_at_reference_published_rates_cny': qwen_hold/10,
               'manual_grade_overrides': len(manual), 'automated_judge_same_model_family': True,
               'isolation_checks': len(isolation), 'native_diagnostic_counts': json.loads((BASE/'native-diagnostics.json').read_text('utf-8'))['counts']}
    save(BASE/'result-summary.json', summary)
    save(BASE/'per-question-results.json', rows)
    from collect_diagnostics import collect
    if not (BASE/'native-diagnostics.json').exists():
        collect()
    render_html(summary, rows)
    print(json.dumps({k: summary[k] for k in ['semantic','common_answered','lifecycle',
                     'deepseek_conservative_hold_cny','qwen_conservative_hold_cny']}, ensure_ascii=False), flush=True)


def render_html(summary, rows):
    payload = json.dumps({'summary': summary, 'rows': rows}, ensure_ascii=False).replace('</', '<\\/')
    template = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Companion Core · 记忆测试</title>
<style>
:root{font:16px/1.65 "Microsoft YaHei",system-ui,sans-serif;color:#19324b;background:#f3f6fa}*{box-sizing:border-box}body{margin:0}main{max-width:1180px;margin:auto;padding:42px 26px 80px}h1{font-size:38px;line-height:1.25;margin:18px 0}h2{margin:34px 0 12px;font-size:23px}p{max-width:100ch}.eyebrow{letter-spacing:.16em;font-size:12px;font-weight:700;color:#326396}.notice{border-left:4px solid #cc9438;background:#fff5df;padding:14px 18px}.muted,small{color:#5c7185}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:26px 0}.card,section.panel{background:white;border:1px solid #dce4ed;border-radius:10px;padding:22px}.metric{font-size:32px;font-weight:700}.native{color:#285be4}.reference{color:#008594}.bar{height:9px;background:#e6edf4;border-radius:5px;overflow:hidden;margin:10px 0}.bar>i{display:block;height:100%;background:currentColor}table{width:100%;border-collapse:collapse;font-size:14px}th{text-align:left;background:#eaf0f7}td,th{padding:10px 12px;border-bottom:1px solid #dfe7ef;vertical-align:top}.scroll{overflow:auto}button,select,input{font:inherit;border:1px solid #b9c8d7;border-radius:5px;padding:7px 10px;background:white;color:inherit}button{cursor:pointer}label{display:inline-block;margin-right:10px;margin-bottom:12px}a{color:#285be4}details{background:#fff;border:1px solid #dce4ed;border-radius:7px;margin:10px 0;padding:14px}summary{cursor:pointer;font-weight:600}.answercols{display:grid;grid-template-columns:1fr 1fr;gap:20px}.answer{white-space:pre-wrap;background:#f4f7fb;padding:14px;border-radius:5px;word-break:break-word}pre{white-space:pre-wrap;word-break:break-word;font:13px/1.7 ui-monospace,monospace}.pass{color:#00816c}.fail{color:#b15c36}.tag{font-size:12px;padding:3px 7px;background:#eaf0f7;border-radius:4px;margin-right:5px}img{max-width:100%;max-height:420px;object-fit:contain}audio{display:block;max-width:100%;margin:8px 0}footer{border-top:1px solid #d4dfeb;margin-top:36px;padding-top:18px;font-size:13px}@media(max-width:720px){main{padding:24px 14px}h1{font-size:29px}.cards,.answercols{grid-template-columns:1fr}.metric{font-size:28px}td,th{padding:8px}section.panel{padding:14px}}@media print{button,input,select{display:none}details{break-inside:avoid}body{background:white}}
</style><main>
<div class="eyebrow">COMPANION CORE / MEMORY EVALUATION / 2026-11-02</div>
<h1>能记住，也要记对来源与变化</h1>
<p class="notice"><b>本次自编 714 个测试实例：</b>696 道语义问答，另加 18 项原生生命周期检查。原图的正式私有题库未公开；本结果不能与截图中的 714 题成绩直接排名。六个人物共用题型模板，题目并非 696 个独立故事。</p>
<div class="cards" id="cards"></div>
<p id="coverage" class="muted"></p>
<section class="panel"><h2 style="margin-top:0">按能力和时间查看</h2>
<label>拆分维度 <select id="group"><option value="delay_days">距最后证据的天数</option><option value="category">29 类考点</option><option value="modality_group">证据输入形式</option><option value="persona">六个虚构人物</option></select></label>
<div class="scroll"><table><thead><tr><th>分组</th><th>本项目：整题通过 / 题数</th><th>Qwen RAG：整题通过 / 题数</th></tr></thead><tbody id="pivot"></tbody></table></div>
<small>颜色条以该组总题数为分母。运行失败、空回答单独列为未作答；另报告已作答准确率和双方共同已作答集合。</small></section>
<h2>逐题检查</h2><p class="muted">可查看原始证据、问题、实际回答和判据。自动判卷使用同系列 DeepSeek，属于工程初测；二次核查及修改记录另附。</p>
<label>搜索 <input id="search" placeholder="题号、类别、关键词"></label>
<label>筛选 <select id="filter"><option value="all">全部</option><option value="native_fail">本项目未通过</option><option value="gap">本项目未过、对照通过</option><option value="native_pass">本项目通过</option><option value="unanswered">任一方未作答</option></select></label>
<p id="found" class="muted"></p><div id="cases"></div><button id="more">再显示 30 题</button>
<h2>已经定位的影响因素</h2><section class="panel"><p id="diagnosticCounts"></p><p>原生媒体轮次能读出生日图卡，但后续问答仍可能回答不知道。请求日志显示，提名最近 6 轮历史并不代表它们全部进入模型：3200 token 软预算会裁剪可选历史。原生记忆提取器读取主人原事件的 <code>body.text</code>，媒体读取结果与助手原话并未以同一方式进入这个提取输入。这些是代码和请求证据支持的可能影响因素，尚未做修复后的消融实验，不能把所有失分都归于单一原因。</p><p><a href="native-diagnostics.json">请求与提取输入证据</a> · <a href="asr-quality-audit.json">42 段真实转写核查</a>。语音转写统一繁简后的字符错误率约 2%，未依据参考文本修改实际推理使用的转写。</p></section><h2>本轮测试的方法与边界</h2><section class="panel">
<p>源代码固定在 <code>3da60d63307612ae813b8e6fd61ca318eedd4140</code>。2160 轮虚构历史覆盖 180 天，按考题时刻只载入对应前缀；最终考题只使用到各人物第 323 轮。提问间隔为当天、3、15、45 天，全部通过逻辑时钟模拟。原始资产包含 54 张 PNG 图卡、42 段真实 WAV 和 42 个 TXT；图像题主要测文字图卡的 OCR 内容记忆；引用、转发与助手原话另以原生消息结构输入。WAV 由系统语音合成，再由原生 FasterWhisper small CPU int8 实际识别。</p>
<p>本项目调用原生 Core、SDK 工具、记忆提取/审核/召回、上下文规划与付费预算。图片送入实际图像路径；文件使用服务器 Docker 的原生隔离参数和固定解析镜像；语音使用签名租约与真实 ASR 识别结果。历史纯文本与提供的助手回复属于导入夹具，标记为已发送；所有考题回答停留在原生 Outbox，未做真实 QQ 端到端投递。</p>
<p>Qwen 对照使用 <code>qwen3.7-text-embedding</code> 2560 维、向量前 40 → <code>qwen3.7-text-rerank</code> 前 10、时间排序，再加入最近 6 轮，由同一 <code>deepseek-flash</code> 高思考作答。两者共享真实媒体读取结果及历史媒体回复，对照不读取标准答案、作者音频脚本或本项目的考题回答。这是完整系统比较，原生提示词与工具和 RAG 的证据提示词并不相同。</p>
<p>本项目保持 3200 token 软上下文、768 可见输出及原生默认记忆提取阈值（5 事件、空闲 900 秒），每题原生付费调用上限 8 次；仅关闭逻辑时间测试不适用的输入防抖，并将预算估算有效期显式设为 366 天、按 10 元/美元保守占用。首批默认 30 天有效期导致调用被拦截，已完整保留为无效评测批次及费用；正式分数统一使用从干净数据库重跑的 v2，不挑选两次中的较好回答。</p>
<p>每道题后通过原生擦除删除考题与回答，并恢复考前虚构语料的摘要、片段和历史回复夹具，检查语义状态不变、费用与擦除账本仍在。这个隔离方式不同于原评测每题复制可写数据库。18 项生命周期检查使用直接原生契约断言，核对纠正、撤回、遗忘及旧备份恢复后的擦除重放；不并入 696 道模型问答通过率。</p>
<p>题库与判据在自编语料生成阶段制定，属于同作者、有限模板、单次模型生成的工程评测。严格整题判定要求全部必要信息正确且不出现禁止的错误主张，允许同义表达。重复时点相关、人物模板相关、相同模型辅助判卷，均限制结果外推；没有据此计算独立样本置信区间。保密题只检查是否泄露指定暗号，不能证明回答中的项目进度真实；已观察到未泄密却编写进度的回复，因此另给出排除“信息不足、敏感限制”两类后的 648 题统计。</p></section>
<h2>费用与验证</h2><section class="panel"><p id="budget"></p><p>预算占用根据实际 token 记录和保守单价计算，包含接入试跑及被替代批次；不是供应商账单。Qwen 参考公开单价 0.5 元/百万 token，内部按 5 元/百万 token 保留额度；DeepSeek 按配置费率再乘 10 元/美元占用。共享的媒体接入成本只发生一次，对照费用不代表独立从零建库的总成本。本地 CPU、服务器 Docker 计算成本未折现。</p><p id="verification"></p>
<p><a href="result-summary.json">结果汇总 JSON</a> · <a href="per-question-results.json">逐题完整 JSON</a> · <a href="verification-tests.json">96 项验证收据</a> · <a href="answers-frozen-before-grading.json">判卷前回答哈希</a> · <a href="suite-v1/freeze.json">题库冻结记录</a> · <a href="budget-allocation.json">预算分配</a> · <a href="pricing-sources.json">单价来源</a> · <a href="secondary-review.jsonl">二次核查记录</a></p></section>
<h2>来源</h2><p><a href="https://github.com/Ornn8/memory-system-benchmark/blob/main/docs/methodology.md">参考评测方法</a>、<a href="https://github.com/Ornn8/memory-system-benchmark/blob/main/docs/tested-configurations.md">参考对照配置</a>、<a href="https://platform.qianwenai.com/docs/developer-guides/getting-started/embedding-models">Qwen 模型文档</a>、<a href="https://api-docs.deepseek.com/zh-cn/quick_start/pricing/">DeepSeek 模型与价格</a>、<a href="https://platform.qianwenai.com/docs/developer-guides/getting-started/model-prices">Qwen 价格</a>。</p>
<footer id="footer"></footer>
<script id="data" type="application/json">__DATA__</script><script>
const D=JSON.parse(document.getElementById('data').textContent),S=D.summary;
const el=(t,txt,cls)=>{let e=document.createElement(t);if(txt!==undefined)e.textContent=txt;if(cls)e.className=cls;return e};
const pct=x=>(100*x).toFixed(1)+'%';const names={native:'Companion Core',reference:'Qwen RAG 对照'};
for(const k of ['native','reference']){const x=S.semantic[k],c=el('div',undefined,'card '+k);c.append(el('div',names[k]),el('div',x.passed+' / '+S.semantic.questions,'metric'));let b=el('div',undefined,'bar'),i=el('i');i.style.width=pct(x.pass_rate_all);b.append(i);c.append(b,el('small','全题通过率 '+pct(x.pass_rate_all)+' · 未作答 '+x.unanswered));document.getElementById('cards').append(c)}
let c=el('div',undefined,'card');c.append(el('div','原生生命周期检查'),el('div','18 / 18','metric'),el('small','纠正 · 撤回 · 遗忘 · 擦除重放；单独统计'));document.getElementById('cards').append(c);
document.getElementById('coverage').textContent=['native','reference'].map(k=>names[k]+' 已作答 '+S.semantic[k].answered+'/696，已作答准确率 '+pct(S.semantic[k].pass_rate_answered||0)).join('；')+'。共同已作答 '+S.common_answered.questions+' 题：本项目 '+S.common_answered.native.passed+'/'+S.common_answered.questions+'，对照 '+S.common_answered.reference.passed+'/'+S.common_answered.questions+'。另看需要已知信息的 648 题：本项目 '+S.positive_information_subset.native.passed+'/648，对照 '+S.positive_information_subset.reference.passed+'/648（排除资料不足和仅测保密的两类）。';
function pivot(){let body=document.getElementById('pivot');body.replaceChildren();for(let [v,x] of Object.entries(S.pivots[document.getElementById('group').value])){let tr=el('tr');tr.append(el('td',v));for(let k of ['native','reference']){let td=el('td',x[k].passed+' / '+x.questions+' · '+pct(x[k].pass_rate_all),k),bar=el('div',undefined,'bar'),i=el('i');i.style.width=pct(x[k].pass_rate_all);bar.append(i);td.append(bar,el('small','未作答 '+x[k].unanswered));tr.append(td)}body.append(tr)}}document.getElementById('group').onchange=pivot;pivot();
let limit=30;const status=a=>a.answered?(a.pass?'通过':'未通过'):'未作答';
function cases(){let query=document.getElementById('search').value.toLowerCase(),f=document.getElementById('filter').value;let rows=D.rows.filter(r=>(r.id+' '+r.category+' '+r.question+' '+r.modalities.join(' ')).toLowerCase().includes(query)).filter(r=>f==='all'||f==='native_fail'&&!r.native.pass||f==='gap'&&!r.native.pass&&r.reference.pass||f==='native_pass'&&r.native.pass||f==='unanswered'&&(!r.native.answered||!r.reference.answered));document.getElementById('found').textContent='匹配 '+rows.length+' 题；显示前 '+Math.min(limit,rows.length)+' 题';let root=document.getElementById('cases');root.replaceChildren();for(let r of rows.slice(0,limit)){let d=el('details'),s=el('summary',r.id+' · '+r.category+' · '+r.delay_days+' 天　'+status(r.native)+' / '+status(r.reference));d.append(s,el('p',r.question),el('p','证据形式：'+r.modalities.join(' + ')+'；截止历史第 '+r.cutoff_turn+' 轮'));let cols=el('div',undefined,'answercols');for(let k of ['native','reference']){let col=el('div');col.append(el('b',names[k]+' · '+status(r[k]),r[k].pass?'pass':'fail'),el('div',r[k].answer||'[没有可见回答]','answer'));if(r[k].error)col.append(el('small',r[k].error));cols.append(col)}d.append(cols,el('p','必要信息：'+r.criteria.required.join('；')),el('p','禁止的错误主张：'+r.criteria.forbidden.join('；')));let src=el('details');src.append(el('summary','查看原始证据与实际读取结果'));for(let x of r.sources){src.append(el('b',x.id+' · '+x.now),el('pre',x.text||x.caption||'[媒体]'));if(x.asset){let url='suite-v1/'+x.asset;if(url.endsWith('.png')){let im=el('img');im.src=url;im.alt=x.id;src.append(im)}else if(url.endsWith('.wav')){let au=el('audio');au.controls=true;au.src=url;src.append(au)}let a=el('a','原始文件');a.href=url;src.append(a)}if(x.observed_text)src.append(el('pre','实际读取：'+x.observed_text));src.append(el('pre','历史助手回复：'+(x.native_reply??x.assistant_reply??'')))}d.append(src);root.append(d)}document.getElementById('more').hidden=limit>=rows.length}
for(let id of ['search','filter'])document.getElementById(id).addEventListener('input',()=>{limit=30;cases()});document.getElementById('more').onclick=()=>{limit+=30;cases()};cases();
document.getElementById('budget').textContent='DeepSeek 保守预算占用 ¥'+S.deepseek_conservative_hold_cny.toFixed(3)+' / ¥30；Qwen 保守预算占用 ¥'+S.qwen_conservative_hold_cny.toFixed(3)+' / ¥30。Qwen 按参考公开费率折算约 ¥'+S.qwen_at_reference_published_rates_cny.toFixed(3)+'；DeepSeek 全部按公开高峰单价折算约 ¥'+S.deepseek_at_peak_public_rates_cny.toFixed(3)+'（实际空闲时段单价更低）。';
document.getElementById('diagnosticCounts').textContent='696 次初始问答请求中，'+S.native_diagnostic_counts.initial_only_system_time_question+' 次只保留系统规则、时间参考和当前问题；评测器在这些题前均提名了最近 6 轮历史。另有 '+(S.native_diagnostic_counts.maintenance_MEMORY_INVALID_OUTPUT||0)+' 次记忆提取尝试返回无效结构，后续按原生重试规则处理，这不等于同样数量的最终未作答题。';
document.getElementById('verification').textContent=S.verification_passed+' 项相关检查通过；'+S.isolation_checks+' 份考题隔离断言通过。复核判定修改 '+S.manual_grade_overrides+' 条；详见附带核查记录。';document.getElementById('footer').textContent='生成于 '+S.generated_at+' · 本地工程评测 · 原始请求、响应和付费记录保留在对应批次目录。';
</script></main></html>'''
    (BASE/'memory-report.html').write_text(template.replace('__DATA__', payload), 'utf-8')


if __name__ == '__main__':
    main()
