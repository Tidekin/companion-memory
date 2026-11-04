"""Read-only frozen cohort, original grade, review, budget and lifecycle reconciliation."""
import json
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime

from grade_blind import ROOT, read, save, sha, validate_run, unresolved_requests
from build_comparison_report import load_data, finance, score, ARMS


def main():
    rows,mapping,raw=load_data()
    configs={a:validate_run(ROOT/"arms"/a) for a in ("old","new")}
    ef=json.loads((ROOT/"execution-freeze.json").read_text("utf-8"))
    for name,digest in ef["files_sha256"].items():assert sha(ROOT/name)==digest,name
    manifests={a:[json.loads(p.read_text("utf-8")) for p in (ROOT/"arms"/a/"results").glob("*/manifest.json")] for a in ("old","new")}
    for a,values in manifests.items():
        assert len(values)==6 and all(r["status"]=="COMPLETED" for r in values),a
    lifecycle={}
    for a in ("old","new"):
        path=ROOT/"arms"/a/"lifecycle.xml";tree=ET.parse(path)
        assert len(list(tree.iter("testcase")))==18 and not any(list(tree.iter(tag)) for tag in ("failure","error","skipped"))
        lifecycle[a]=dict(passed=18,total=18,xml_sha256=sha(path))
    requests=read(ROOT/"grading/requests.jsonl");responses=read(ROOT/"grading/responses.jsonl")
    assert not unresolved_requests(requests,responses)
    keys=[k for r in requests for k in r["keys"]]
    assert len(keys)==len(set(keys))==2078
    assert len(responses)==len({r["batch_id"] for r in responses})==len(requests)
    assert all(r["status"]==200 for r in responses)
    assert json.loads((ROOT/"grading/manifest.json").read_text("utf-8"))["raw_grades_sha256"]==sha(ROOT/"grading/grades.jsonl")
    states={a:dict(Counter(r["arms"][a]["status"] for r in rows)) for a in ARMS}
    assert states=={"old":{"SUCCEEDED":693,"CANCELLED":3},"new":{"SUCCEEDED":689,"CANCELLED":7},"rag":{"SUCCEEDED":696}}
    assert len(mapping)==len(raw)==2088
    assert len({r["category_id"] for r in rows})==29
    assert Counter(r["delay_days"] for r in rows)=={0:174,3:174,15:174,45:174}
    for a in ARMS:
        for r in rows:
            if r["arms"][a]["status"]!="SUCCEEDED":assert not r["arms"][a]["passed"]
    fees={"deepseek":finance("deepseek-usage.jsonl",50),"qwen":finance("qwen-usage.jsonl",30)}
    assert fees["deepseek"]["states"].get("UNKNOWN")==15
    assert abs(fees["deepseek"]["unknown_held_cny"]-1.499256)<1e-8
    coverage=dict(status="PASSED",at=datetime.now(UTC).isoformat(),semantic_per_arm=696,total_answers=2088,
                  source_commits={a:c["source_commit"] for a,c in configs.items()},
                  states=states,lifecycle=lifecycle,all_answer_hashes_verified=True,
                  source_and_corpus_and_execution_freezes_verified=True,
                  raw_grades_sha256=sha(ROOT/"grading/grades.jsonl"),
                  review_sha256=sha(ROOT/"assistant-grade-review.jsonl") if (ROOT/"assistant-grade-review.jsonl").exists() else None,
                  fees=fees,judge_requests=len(requests),zero_judge_replay=True,
                  unknowns_retained_and_not_double_counted=True,
                  failure_denominator=696,grades={a:score(rows,a) for a in ARMS},
                  evidence_sha256={n:sha(ROOT/n) for n in ("source-freeze.json","corpus-freeze.json","execution-freeze.json","campaign-freeze.json","all-answers-frozen.json","deepseek-usage.jsonl","qwen-usage.jsonl")})
    save(ROOT/"coverage-and-freeze.json",coverage)
    print('COVERAGE_FREEZE_BUDGET_PASSED',fees['deepseek']['charged_or_held_cny'])


if __name__=="__main__":main()
