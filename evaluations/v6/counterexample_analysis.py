"""Read-only request provenance for a small disclosed set of remaining errors."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def rows(path):
    return [json.loads(x) for x in path.read_text('utf-8').splitlines() if x.strip()]


def main():
    results = {r['id']: r for r in json.loads((ROOT / 'results.json').read_text('utf-8'))}
    cases = []
    for case, terms, diagnosis in (
        ('X06-C23/d03', ['韦葵'], '确定性上下文丢失：原请求有转述人，工具续接后原文组被裁掉。已另行合成修复，不重算冻结分数。'),
        ('X05-C14/d00', ['不是我弟弟'], '最终请求仍有否定归属，回答却混淆主人与朋友的弟弟；属于回答生成错误。'),
        ('X03-C07/d15', ['137', '47'], '原始数值已在请求中，回答算87而正确差值90；属于计算生成错误。'),
        ('X03-C30/d45', ['没挑中'], '最后请求仍有未选中状态，但回答没有保留；不能归因为来源未进上下文。'),
        ('X01-C26/d00', [], '复述了被要求不要再说的合成暗号；本题仅测试输出不复述，不能认证存储擦除。'),
    ):
        path = ROOT / 'arms/new/results' / case.split('-')[0] / 'requests.jsonl'
        requests = [r for r in rows(path) if r.get('phase') == 'exam' and r.get('case') == case]
        assert requests
        counts = [{term: json.dumps(r['payload']['messages'], ensure_ascii=False).count(term)
                   for term in terms} for r in requests]
        cases.append({'id': case, 'arm': 'new', 'passed': results[case]['arms']['new']['passed'],
                      'answer': results[case]['arms']['new']['answer'], 'diagnosis': diagnosis,
                      'request_file': path.relative_to(ROOT).as_posix(),
                      'request_file_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                      'per_request_term_counts': counts})
    assert cases[0]['per_request_term_counts'] == [{'韦葵': 4}, {'韦葵': 0}]
    for case in cases[1:4]:
        assert all(value > 0 for value in case['per_request_term_counts'][-1].values())
    out = {'scope': 'Post-hoc case diagnosis, not error-rate estimation; no new provider calls.',
           'benchmark_candidate': '7074838d13336240968d39b0299ada126b610b99', 'cases': cases}
    (ROOT / 'counterexamples.json').write_text(json.dumps(out, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    print([(c['id'], c['per_request_term_counts']) for c in cases])


if __name__ == '__main__':
    main()
