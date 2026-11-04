"""Post-hoc, uniformly applied validity and interpretation checks; primary inputs stay frozen."""
import copy
import hashlib
import importlib.util
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(name):
    return json.loads((ROOT / name).read_text('utf-8'))


def rows(path):
    return [json.loads(line) for line in path.read_text('utf-8').splitlines() if line.strip()]


def save(name, value):
    (ROOT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf-8')


def main():
    results = load('results.json')
    spec = importlib.util.spec_from_file_location('frozen_paired_formula', ROOT / 'paired_analysis.py')
    paired = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(paired)
    observed = {r['id']: r for p in (ROOT / 'arms/old/results').glob('*/turns-observed.jsonl')
                for r in rows(p)}
    findings = []
    for category, kind, issue in (
        ('C13', 'authoring_name_mismatch', '题干霜叶清册与图片/实际读取的榆叶工具清册不一致。'),
        ('C21', 'authoring_name_mismatch', '计划为岚屿交流函，未寄出的更新却称星屿那封，未说明二者同一。'),
        ('C18', 'temporal_anchor_ambiguity', '语音自述今天3月21日，入站时间3月30日；记录时间与接收时间未另作说明。'),
    ):
        mine = [r for r in results if r['category_id'] == category]
        assert len(mine) == 24
        sample = next(r for r in mine if r['id'] == f'X01-{category}/d00')
        findings.append({'category': category, 'kind': kind, 'issue': issue,
                         'question_ids': [r['id'] for r in mine],
                         'example': {'question': sample['question'], 'sources': sample['sources'],
                                     'observed': [observed[key] for key in sample['source_ids']]}})
    save('question-validity-audit.json', {
        'posthoc': True, 'primary_unchanged': True, 'uniform_all_arms': True,
        'findings': findings, 'additional_scoring_limits': [
            'C22的借某人N把没有明确借入或借出，现有得分不能认证借用方向。',
            'C24要求纸鸟身份却未明确写搭档归属，漏答搭档仍可能满足冻结required。',
            'C26只检查回答不复述，不证明存储中已擦除；擦除另由产品测试验证。']})
    subsets = {
        'without_name_mismatches_C13_C21': [r for r in results if r['category_id'] not in {'C13', 'C21'}],
        'without_names_and_C18_anchor': [r for r in results if r['category_id'] not in {'C13', 'C18', 'C21'}],
        'without_names_C18_and_C17': [r for r in results if r['category_id'] not in {'C13', 'C17', 'C18', 'C21'}],
        'without_C12': [r for r in results if r['category_id'] != 'C12'],
    }
    broad = copy.deepcopy(results)
    contested = []
    for row in broad:
        if row['category_id'] != 'C12':
            continue
        for arm, value in row['arms'].items():
            if value['passed'] != value['auto_grade']['pass']:
                contested.append({'id': row['id'], 'arm': arm, 'key': value['key'],
                                  'strict_pass': value['passed'],
                                  'raw_C12_pass': value['auto_grade']['pass'],
                                  'answer': value['answer']})
            value['passed'] = value['auto_grade']['pass']
    subsets['restore_raw_majority_only_for_C12'] = broad
    review = rows(ROOT / 'grading/review.jsonl')
    save('review-semantic-boundaries.json', {
        'C12': {'posthoc': True, 'interpretation': '较严复核把未经授权按后值为准视为消解冲突；仅禁止明确宣告作废的文字口径可能不同。',
                'scope': '所有C12、所有四臂都已复核；宽口径仅恢复C12原始多数票，其他改判不变。',
                'contested': contested},
        'C17': {'handling': '名称只是未确认猜测的部分回答存在判分边界；不强改原多数票，报告预注册非C17敏感性。',
                'reviewed_boundary_keys': [r['key'] for r in review if 'C17' in r['reason'] and '边界' in r['reason']]}})
    save('validity-sensitivity.json', {
        'posthoc': True, 'primary_unchanged': True, 'uniform_all_arms': True,
        'results_sha256': hashlib.sha256((ROOT / 'results.json').read_bytes()).hexdigest(),
        'interpretation': '输入缺陷与评分解释敏感性，非新的预注册主指标，不能挑选较好子集替代主分数。',
        'subsets': {name: paired.summarize(value) for name, value in subsets.items()}})
    failures = {}
    for arm in ('old', 'new'):
        audit, invalid, retained, checkpoints = Counter(), Counter(), [], []
        for path in sorted((ROOT / f'arms/{arm}/results').glob('*/core.sqlite3')):
            con = sqlite3.connect(f'file:{path.resolve().as_posix()}?mode=ro', uri=True)
            for action, detail in con.execute(
                    "SELECT action,safe_detail_json FROM audit_log WHERE action IN ('memory.batch_failed','memory.review_invalid')"):
                audit[action] += 1
                if action == 'memory.review_invalid':
                    invalid[json.loads(detail)['reason']] += 1
            for key, value in con.execute(
                    "SELECT key,value FROM runtime_meta WHERE key LIKE 'memory_failed_batch:%' OR key='memory_extraction_checkpoint'"):
                record = json.loads(value)
                batch = record['batch']
                if key == 'memory_extraction_checkpoint':
                    checkpoints.append({'persona': path.parent.name, 'phase': batch['phase']})
                    continue
                receipts = [dict(zip(('request_id', 'state'), row)) for row in con.execute(
                    'SELECT request_id,state FROM model_usage WHERE request_id IN (?,?)',
                    (batch.get('request_id'), batch.get('extraction_request_id')))]
                retained.append({'persona': path.parent.name, 'entry': key, 'state': record['state'],
                    'recoveries': record['recoveries'], 'candidates': len(batch.get('candidates', [])),
                    'source_count': len(record['source_event_ids']), 'error': batch.get('error'),
                    'review_attempts': batch.get('review_attempts'), 'receipts': receipts})
            con.close()
        failures[arm] = {'attempt_events': dict(audit), 'review_invalid_reasons': dict(invalid),
                         'retained_terminal_failures': retained, 'current_checkpoints': checkpoints}
    save('failure-diagnosis.json', {'method': '只读闭合数据库；batch_failed为失败尝试事件，不是终态批次数。',
                                    'explicit_recovery_executed': False, 'arms': failures})
    print(json.dumps({k: v['accuracy'] for k, v in load('validity-sensitivity.json')['subsets'].items()}))


if __name__ == '__main__':
    main()
