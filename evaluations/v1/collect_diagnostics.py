"""Read-only causal breadcrumbs, kept separate from answer grading."""
import json
import sqlite3
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent


def rows(p):
    return [json.loads(s) for s in p.read_text('utf-8').splitlines()]


def collect():
    counts = Counter()
    examples = []
    state_counts = Counter()
    for directory in sorted((BASE/'native-final-v2').glob('P*')):
        answers = {r['id']: r for r in rows(directory/'answers.jsonl')}
        observed = {r['id']: r for r in rows(directory/'turns-observed.jsonl')}
        initial = {}
        extraction = {}
        maintenance_errors = Counter()
        for r in rows(directory/'requests.jsonl'):
            if r['phase'] == 'exam':
                initial.setdefault(r['case'], r)
            if r['phase'] == 'maintenance':
                messages = r['payload'].get('messages', [])
                if len(messages) == 2:
                    try:
                        body = json.loads(messages[1]['content'])
                    except (ValueError, TypeError):
                        continue
                    if isinstance(body, list):
                        for event in body:
                            if isinstance(event, dict) and 'event_id' in event and 'text' in event:
                                extraction.setdefault(event['event_id'], event['text'])
        for qid, r in initial.items():
            a = answers[qid]
            messages = r['payload']['messages']
            counts['initial_requests'] += 1
            counts['nominated_six_history_turns'] += a['short_term_turns'] == 6
            counts['initial_only_system_time_question'] += len(messages) == 3
        for r in rows(directory/'maintenance.jsonl'):
            if not r['success']:
                maintenance_errors[(r.get('checkpoint') or {}).get('batch', {}).get('error', 'NONCOMPLETE')] += 1
        for key, n in maintenance_errors.items():
            counts['maintenance_'+key] += n
        conn = sqlite3.connect(f'file:{(directory/"core.sqlite3").as_posix()}?mode=ro', uri=True)
        for state, n in conn.execute('SELECT status,count(*) FROM memories GROUP BY status'):
            state_counts[state] += n
        counts['traits_remaining'] += conn.execute('SELECT count(*) FROM traits').fetchone()[0]
        conn.close()
        pid = directory.name
        source = observed[pid+'-C02-S1']
        qid = pid+'-C02/d00'
        q = answers[qid]
        request = initial[qid]
        examples.append({
            'question_id': qid, 'question': q['question'],
            'source_asset': source['asset'], 'native_media_reply': source['native_reply'],
            'native_question_answer': q['answer'], 'native_question_state': q['status'],
            'nominated_history_count': q['short_term_turns'],
            'first_request_messages': request['payload']['messages'],
            'first_request_tool_count': len(request['payload'].get('tools', [])),
            'extractor_text_for_original_image': extraction.get(source['event_id']),
        })
    value = {'classification': 'READ_ONLY_OBSERVATIONS_NOT_A_CONTROLLED_FIX_EXPERIMENT',
             'counts': dict(counts), 'final_memory_states': dict(state_counts),
             'birthday_image_examples': examples,
             'source_locations': {'extractor_input': 'companion/memory_work.py:576-592',
                                  'context_soft_limit': 'companion/context_planner.py:27-41',
                                  'context_drop_loop': 'companion/context_planner.py:333-393'},
             'interpretation': [
                 'Birthday images were visibly read during original native media turns; the later question may still lack that fact.',
                 'Native extraction inputs use owner event body.text, while observed media contents live in other native projections.',
                 'A nominated history count does not prove that history survived native context planning; inspect actual request messages.',
                 'No production fix was applied and no ablation rerun was performed; these observations identify likely contributors, not measured improvement.',
             ]}
    (BASE/'native-diagnostics.json').write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    print(json.dumps(value['counts']), flush=True)
    return value


if __name__ == '__main__':
    collect()
