"""Seal one final round receipt and a hash-verified, credential-scanned synthetic evidence ZIP."""
import hashlib
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from grade_blind import ROOT, read, save, sha
from scripts.memory_benchmark.runtime import credential


def eligible(path):
    rel=path.relative_to(ROOT)
    if any(part in {".cache","__pycache__",".git","vectors","node_modules"} or "sqlite" in part.lower() for part in rel.parts):
        return False
    if path.suffix.lower() in {".pyc",".zip",".lock",".db",".db-wal",".db-shm"} or path.name.startswith('.env'):
        return False
    if path.name in {"verification-receipt.json","package-integrity.json","package-members.json",
                     "pipeline-status.json","monitor-state.json","review-notes-in-progress.json"}:
        return False
    return not path.is_symlink()


def main():
    assert not (ROOT/"verification-receipt.json").exists(),"Final receipt already sealed; inspect rather than overwrite"
    assert not (ROOT/"companion-memory-comparison-20261102.zip").exists()
    summary=json.loads((ROOT/"summary.json").read_text('utf-8'))
    audit=json.loads((ROOT/"coverage-and-freeze.json").read_text('utf-8'))
    visual=json.loads((ROOT/"final-review.json").read_text('utf-8'))
    ui=json.loads((ROOT/"report-ui-verification.json").read_text('utf-8'))
    assert visual['status']=='COMPLETE' and ui['status']=='PASSED' and audit['status']=='PASSED'
    assert audit['grades']==summary['overall'] and audit['fees']==summary['finance']
    for name,digest in audit['evidence_sha256'].items():assert sha(ROOT/name)==digest,name
    for name,digest in visual['images_inspected'].items():assert sha(ROOT/name)==digest,name
    assert sha(ROOT/'memory-report.html')==visual['html_sha256']==ui['html_sha256']
    reviews=read(ROOT/'assistant-grade-review.jsonl')
    assert len(reviews)==len({r['key'] for r in reviews})==116
    assert sum(r['id'].startswith('N02-') and r['id'].endswith('/d15') for r in reviews)==87
    assert len(read(ROOT/'grade-review-overrides.jsonl'))==9
    assert sha(ROOT/'grading/grades.jsonl')==audit['raw_grades_sha256']
    config=json.loads((ROOT/'arms/old/run.json').read_text('utf-8'))
    pixel_text=(Path.home()/'Desktop/Pixel.txt').read_text('utf-8-sig')
    pixel=re.search(r'sk-[A-Za-z0-9_.-]+',pixel_text)
    assert pixel
    secrets=[credential(config),(Path.home()/'Desktop/千问Key.txt').read_text('utf-8-sig').strip(),pixel.group()]
    assert all(len(s)>=12 for s in secrets)
    patterns=[s.encode() for s in secrets]
    files=sorted(p for p in ROOT.rglob('*') if p.is_file() and eligible(p))
    for p in files:
        blob=p.read_bytes()
        assert not any(k in blob for k in patterns),'Credential content found in '+str(p.relative_to(ROOT))
    members={p.relative_to(ROOT).as_posix():sha(p) for p in files}
    save(ROOT/'package-members.json',dict(files_sha256=members,exclusions=[
        'SQLite/databases including owner-images cache','runtime/vector/browser caches',
        'credential/env files','locks/bytecode','final receipt and ZIP integrity outsideZIP to avoid circular hashes'],
        production_data_included=False,synthetic_materials_only=True))
    files.append(ROOT/'package-members.json')
    package=ROOT/'companion-memory-comparison-20261102.zip'
    with zipfile.ZipFile(package,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for p in files:archive.write(p,p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist())==len(set(archive.namelist()))==len(files)
        for name in archive.namelist():
            assert name=='package-members.json' or eligible(ROOT/name),name
            blob=archive.read(name)
            assert not any(k in blob for k in patterns),'Credential content in ZIP member '+name
            if name!='package-members.json':assert hashlib.sha256(blob).hexdigest()==members[name]
    integrity=dict(status='PASSED',zip=package.name,sha256=sha(package),bytes=package.stat().st_size,
                   members=len(files),zip_testzip='PASSED',all_member_hashes='PASSED',
                   actual_three_credential_content_scan='PASSED',credential_values_not_recorded=True)
    save(ROOT/'package-integrity.json',integrity)
    receipt=dict(status='COMPLETE_VERIFIED',at=datetime.now(UTC).isoformat(),
                 round='memory-blind-comparison-20261102',source_commits=audit['source_commits'],
                 source_frozen_before_new_bank=True,answers_frozen_before_gold_read=True,
                 semantic_questions_per_arm=696,answers=2088,primary=summary['overall'],
                 delta_percentage_points=summary['new_minus_old_percentage_points'],
                 paired_changes=summary['paired_changes'],source_ambiguity_sensitivity=summary['source_ambiguity_sensitivity'],
                 lifecycle=audit['lifecycle'],finance=summary['finance'],
                 codex_reviewed=116,separate_grade_overrides=9,independent_human_judging=False,
                 html_ui_checks=ui,visual_inspection=visual,
                 source_checks_reused='source-materials/new-source-check-qualification.json',
                 runner_checks_reused='source-materials/reusable-runner-verification.json',
                 new_budget_and_boundaries_checks=6,new_judge_checks=3,new_report_aggregation_checks=2,
                 production_modified=False,real_qq_sent=False,inference_replayed=False,
                 evidence_sha256=audit['evidence_sha256'],coverage_audit_sha256=sha(ROOT/'coverage-and-freeze.json'),
                 package=integrity,limitations=summary['limitations']+[
                     'K23source pronoun ambiguity affects24questions per arm; primary unchanged, common672question sensitivity disclosed.',
                     'Frozen rubric labels and Codex overrides are inspectable; unreviewed model-judge mistakes may remain.'])
    save(ROOT/'verification-receipt.json',receipt)
    save(ROOT/'pipeline-status.json',dict(status='COMPLETE_VERIFIED',at=receipt['at'],receipt='verification-receipt.json'))
    print('COMPLETE_VERIFIED',summary['overall'],integrity['members'],integrity['bytes'])


if __name__=='__main__':main()
