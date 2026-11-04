"""Offline reviewed report overlay. Frozen experiment inputs and raw grades stay intact."""
import html
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
for name in ('MPLCONFIGDIR', 'TEMP', 'TMP'):
    destination = ROOT / '.cache' / name.lower()
    destination.mkdir(parents=True, exist_ok=True)
    os.environ[name] = str(destination)
sys.path.insert(0, str(WORKSPACE / '.local/memory-accuracy-v5-20261103/.deps'))
sys.argv = [__file__, '--round', str(ROOT)]
spec = importlib.util.spec_from_file_location(
    'v6_reviewed_report', WORKSPACE / 'benchmarks/memory_campaign/report.py')
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


def load(name):
    return json.loads((ROOT / name).read_text('utf-8'))


def pct(value):
    return f'{value:.2%}'


def main():
    rows, grades = P.load()
    selection = P.prepare_review(rows, grades)
    reviewed = {x['key'] for x in P.read_rows(P.GRADING / 'review.jsonl')}
    uncertain = {x['key'] for n in (1, 2, 3)
                 for x in P.read_rows(P.GRADING / f'vote-{n}/grades.jsonl')
                 if x.get('anchor_failed') or x.get('judge_unresolved')}
    assert {x['key'] for x in selection} | uncertain <= reviewed
    summary = P.summarize(rows)
    summary['overall']['closed'] = P.score(rows, 'closed')
    main_finance = summary['finance']['deepseek']
    smoke = P.finance(ROOT / 'smoke/deepseek-usage.jsonl', 1)
    combined = main_finance['charged_or_held_cny'] + smoke['charged_or_held_cny']
    assert combined <= 80
    summary['finance']['deepseek'] = {
        **main_finance, 'charged_or_held_cny': combined, 'cap_cny': 80,
        'main_only': main_finance, 'smoke': smoke, 'invoice_verified': False}
    summary['by_persona'] = {p: {a: P.score([r for r in rows if r['persona'] == p], a)
                                 for a in P.R.graded_arms} for p in P.R.personas}
    summary['review_any_vote_uncertain'] = len(uncertain)
    P.save(ROOT / 'results.json', rows)
    subprocess.run([sys.executable, '-B', str(ROOT / 'paired_analysis.py'),
                    '--round', str(ROOT)], check=True, stdout=subprocess.DEVNULL)
    paired = load('paired-analysis.json')
    summary['paired_analysis'] = paired
    summary['runtime'] = load('native-runtime-metrics.json')['summary']
    summary['post_evaluation_repair'] = load('post-evaluation-verification.json')
    summary['validity_sensitivity'] = load('validity-sensitivity.json')
    summary['failure_diagnosis'] = load('failure-diagnosis.json')
    summary['raw_majority'] = {a: sum(row['arms'][a]['auto_grade']['pass'] for row in rows)
                               for a in P.R.graded_arms}
    summary['limitations'] += [
        '三票中的两票使用同一DeepSeek模型；跨供应商不等于三个独立判官。曝光锚点过门槛不能保证每题判对。',
        '字段诊断是同一证据单元内的词串启发式；有一条来源引用只说明抽取过部分材料，不代表全部评分事实完整入库。',
        '同一版本链的四种视角占96次提问、仅6条链；细类每时间档只有6个人物事实组。区间为探索性描述。',
        'C17的24个语音问题保留真实ASR同音错误；主分数保留全部题，同时报告预先指定的非C17子集。',
        '按冻结的v3规则评必需与禁止项；额外未列为禁止项的说法可能不直接判错，得分不等于零幻觉率。',
        'C13和C21各24题存在作者命名不一致；C18另24题有语音日期与接收时间歧义。主分数保持冻结，另对所有臂统一做事后敏感性。',
        'C12复核较严解释未经确认就采用后值，较宽文字口径可能不同；单独恢复C12原多数票时，新旧差距从2.15缩小到1.14个百分点。',
        '评测候选7074838d之后发现原文续接裁剪缺陷，另在8e91e276补修并通过90项定向检查；没有重跑付费评测，不能把原分数当作补修版成绩。',
    ]
    P.save(ROOT / 'summary.json', summary)
    figures = P.charts(rows, summary)
    assert len(figures) == 8
    P.render(rows, summary, figures)
    e = lambda value: html.escape(str(value))
    subsets = paired['subsets']
    analysis = ['<section class="analysis"><h2>结论与证据</h2>',
                '<p><strong>本轮支持继续做真实聊天验证，尚不能证明新版整体更强。</strong>'
                '复核后净增17题、+2.15个百分点；事实组与人物聚类区间都包含零。'
                '千问RAG仍高于新版；合成自然聊天48题从47题通过降至45题。</p>',
                '<p>比较冻结的旧版86aa9e46与修复版7074838d；全部回答先冻结，再由固定盲判三票评判。'
                '以下为叠加同一助手复核后的结果，原始判分和每条改判理由均保留。</p>',
                '<p>最终交付源码为8e91e276：另修了“原文已选入首请求，但工具续接后丢失转述人”的确定性缺陷。'
                '复用既有来源组标记，无新模型或协议；已通过合成定向检查，没有重跑此题答案或整轮评测。'
                '<a href="post-evaluation-verification.json">补修验证回执</a></p>',
                '<table><thead><tr><th>范围</th><th>实例 / 事实组</th><th>旧版</th><th>新版</th>'
                '<th>RAG</th><th>变为通过 / 未通过</th></tr></thead><tbody>']
    names = {'all': '全部', 'non_C17': '排除C17语音', 'C28_chains': '版本链四视角',
             'without_C28': '除版本链', 'natural_C29_C30': '合成自然聊天'}
    for key, label in names.items():
        value = subsets[key]
        change = value['paired_changes']
        analysis.append(f'<tr><td>{e(label)}</td><td>{value["instances"]} / '
                        f'{value["fact_groups"]}</td>' + ''.join(
                            f'<td>{pct(value["accuracy"][a])}</td>' for a in P.ARMS)
                        + f'<td>+{change.get("gain", 0)} / −{change.get("loss", 0)}</td></tr>')
    analysis.append('</tbody></table>')
    for key, label in (('fact_group', '180个事实组'), ('persona', '6个人物')):
        ci = subsets['all'][key]['new_minus_old_points_95_ci']
        analysis.append(f'<p>按{label}进行配对聚类自助抽样（固定种子，20,000次）：'
                        f'新版减旧版的探索性95%区间为{ci[0]:+.2f}至{ci[1]:+.2f}个百分点。'
                        '人物和模板仍相关，不能据此推断总体因果效应。</p>')
    analysis.append('<p>RAG使用千问向量与重排，再使用同一个DeepSeek生成器；闭卷对照无材料。'
                    '自然聊天48次提问来自12组新编故事，真实主人聊天仍待实际交互。</p>')
    analysis.append('<h2>原始判分、复核与边界</h2><table><thead><tr><th>臂</th>'
                    '<th>原始三票多数</th><th>同一助手复核后</th></tr></thead><tbody>')
    for arm in P.R.graded_arms:
        reviewed_score = summary['overall'][arm]
        raw = summary['raw_majority'][arm]
        analysis.append(f'<tr><td>{e(P.LABELS[arm])}</td><td>{raw}/792 · {raw/792:.2%}</td>'
                        f'<td>{reviewed_score["passed"]}/792 · {reviewed_score["rate"]:.2%}</td></tr>')
    analysis.append('</tbody></table><p>复核766份，改判98份；包括固定选择、任意一票锚失败或未决项，'
                    '以及全部四臂的C03/C12。复核者也是题库作者和修复者，属于同一助手审阅。'
                    '三票为DeepSeek/DeepSeek/Qwen，两个DeepSeek投票并不独立。'
                    '三票曝光锚准确率分别78.25%、76.54%、79.01%，均过预定门槛；不能据此保证每题正确。</p>')
    analysis.append('<p>C03题干已给出单位，回答职位即可满足语义；所有臂统一处理。'
                    'C12把“未确认仍按后值为准”视作消解冲突，是较严解释；冻结文字只明确禁止宣告前值作废，'
                    '较宽解释可能通过。全部C12均复核，以下同时列出恢复该类原始多数票的结果。'
                    'C17猜测性名称存在判分边界，保留原多数票并报告预注册非C17子集。'
                    '<a href="review-semantic-boundaries.json">边界与原回答</a></p>')
    analysis.append('<h2>作者缺陷与事后敏感性</h2><p>题库由我编写，发现两处命名错误：'
                    'C13题干“霜叶清册”与图片“榆叶工具清册”不一致；C21“岚屿交流函”的后续却写成“星屿那封”，'
                    '没有明确同一关系。各影响24个实例。C18另24题的语音自述今天3月21日，但入站日期3月30日，'
                    '时间锚不清。下面统一应用到所有臂，属于事后分析，主分数仍保留792题。'
                    '<a href="question-validity-audit.json">题目审计</a></p>')
    analysis.append('<table><thead><tr><th>事后范围</th><th>题数</th><th>旧版</th><th>新版</th>'
                    '<th>RAG</th><th>差值95%区间 / pp</th></tr></thead><tbody>')
    labels = {'without_name_mismatches_C13_C21': '排除C13/C21命名错误',
              'without_names_and_C18_anchor': '再排除C18时间歧义',
              'without_names_C18_and_C17': '再排除C17真实ASR',
              'without_C12': '仅排除C12争议类',
              'restore_raw_majority_only_for_C12': '仅C12恢复原多数票'}
    for key, label in labels.items():
        value = summary['validity_sensitivity']['subsets'][key]
        ci = value['fact_group']['new_minus_old_points_95_ci']
        analysis.append(f'<tr><td>{e(label)}</td><td>{value["instances"]}</td>' + ''.join(
            f'<td>{pct(value["accuracy"][a])}</td>' for a in P.ARMS) +
            f'<td>{ci[0]:+.2f} 至 {ci[1]:+.2f}</td></tr>')
    analysis.append('</tbody></table><p>所有这些区间仍包含零。C22“借某人”未限定借入/借出，'
                    'C24必需项未明确搭档归属，C26只测回答不复述，均限制结论；通过率不能认证这些能力。'
                    '全部输入、答案及原始判分保留，不用有利子集替代主结果。</p>')
    analysis.append('<h2>漏存、失败恢复与剩余错误</h2><p>原生批次失败审计事件：旧版12次、新版37次，'
                    '这是失败尝试数，不能当终态失败批次数。新版有2个保留的FAILED批次（共4个候选），'
                    '来源证明和已结算请求均保留，恢复计数为0；六个人物当前检查点均完成。'
                    '本轮没有调用显式恢复，不能宣称测得恢复成功率。恢复API的有界、UNKNOWN和擦除合同'
                    '由合成入口/独立worker测试验证。<a href="failure-diagnosis.json">只读失败诊断</a></p>')
    analysis.append('<p>严格审查输出仍有无效关系：旧版10次（7个格式、3个引用错误），'
                    '新版16次（7个格式、9个替换引用错误）；新版并未降低这类失败次数。'
                    '启发式“所有可检查字段在提示中”是旧版91.9%、新版92.8%，有236项标准无法词串检查，'
                    '该数不是语义召回率或完整入库率。</p>')
    analysis.append('<ul>')
    for case in load('counterexamples.json')['cases']:
        analysis.append(f'<li><code>{e(case["id"])}</code>：{e(case["diagnosis"])}</li>')
    analysis.append('</ul><p><a href="counterexamples.json">逐请求来源计数与回答</a>；'
                    '剩余生成错误保留，本轮没有针对答案加特判。</p>')
    analysis.append('<p>DeepSeek含主账与冒烟合计¥'
                    f'{combined:.4f}/¥80（主账¥{main_finance["charged_or_held_cny"]:.4f}/¥79，'
                    f'冒烟¥{smoke["charged_or_held_cny"]:.4f}/¥1）；千问¥'
                    f'{summary["finance"]["qwen"]["charged_or_held_cny"]:.4f}/¥80。'
                    '包含各臂、判官、有界锚重试及不确定请求，按保守费率估算，未核供应商发票。</p>')
    analysis.append('<p>首个冻结候选af3c1869做了唯一一次仓库全量检查：10,361通过、60跳过、17失败；'
                    '17项均在后续定向检查通过。最终7074838d的规范键/历史、SDK、配置与入口定向检查分别'
                    '通过62、67、85项；评测后补修8e91e276另通过90项相关检查和200项文档检查，'
                    '未再运行全量。独立worker和真实HTTP入口的失败恢复合成检查通过。'
                    '本报告未执行生产发布或真实QQ聊天验收。</p></section>')
    page = (ROOT / 'memory-report.html').read_text('utf-8')
    page = page.replace('<meta charset="utf-8">', '<meta charset="utf-8">'
                        '<meta name="viewport" content="width=device-width,initial-scale=1">')
    page = page.replace('题 × 旧版 / 新版 / 千问RAG', '题 × 旧版 / 新版 / 千问RAG / 闭卷对照')
    page = page.replace('非独立人工。', '由同一助手复核。')
    diagnostics = P.extras(summary, e)
    assert diagnostics and diagnostics in page
    page = page.replace(diagnostics, ''.join(analysis) + '<details class="diagnostics">'
                        '<summary>展开锚点、逐字核对与完整分层诊断</summary>'
                        + diagnostics + '</details>', 1)
    css = '''*{box-sizing:border-box}body{overflow-wrap:anywhere}main{min-width:0}
    .kpis,.answers{grid-template-columns:repeat(3,minmax(0,1fr))}.answer{min-width:0}
    .analysis{background:white;padding:20px;margin:24px 0;line-height:1.65}
    table{border-collapse:collapse;width:100%;font-size:14px}th,td{border-bottom:1px solid #d1dce9;padding:8px;text-align:left}
    code{word-break:break-all}summary{cursor:pointer;line-height:1.6}pre{overflow-wrap:anywhere}
    @media(max-width:650px){main{padding:16px}.kpis,.answers{grid-template-columns:1fr}
    h1{font-size:25px}.analysis{padding:12px}th,td{padding:5px;font-size:11px}figure{padding:4px}}
    '''
    page = page.replace('</style>', css + '</style>')
    (ROOT / 'memory-report.html').write_text(page, 'utf-8')
    print(json.dumps(summary['overall'], ensure_ascii=False))


if __name__ == '__main__':
    main()
