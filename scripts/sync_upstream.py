"""Export committed public memory sources and regenerate the executable reference helpers."""

import argparse
import ast
import copy
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "https://github.com/Tidekin/companion-core"
EXTRA = {
    "companion/contracts.py",
    "companion/retrieval.py",
    "companion/reranker.py",
    "companion/turn_recall.py",
    "companion/dialogue_history.py",
    "companion/context_selection.py",
    "companion/context_planner.py",
    "companion/agent_messages.py",
    "companion/agent_tools.py",
    "companion/privacy.py",
    "companion/erasure.py",
    "companion/store.py",
    "companion/owner_authority.py",
    "companion/owner_input.py",
    "companion/reply_revision.py",
    "companion/budget.py",
    "companion/paid_budget.py",
    "companion/nightly_stages.py",
    "companion/worker_schedule.py",
    "tests/fixtures/memory-recall-probes-v1.json",
    "docs/plans/2026-11-04-memory-reliability.md",
    "docs/plans/2026-11-02-memory-inputs.md",
    "docs/qq-beta/p11-history-memory-composition.md",
}
MODEL_CLASSES = (
    "StrictModel",
    "Candidate",
    "EpisodeSummary",
    "InteractionSignal",
    "Extraction",
    "MemoryRelation",
    "MemoryReview",
    "MemorySelection",
    "CoreError",
)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def git(source, *args):
    return subprocess.check_output(["git", "-C", str(source), *args])


def selected(path):
    return (
        path in EXTRA
        or path.startswith("companion/memory")
        and path.endswith(".py")
        or path.startswith("tests/test_")
        and "memory" in path
        and path.endswith(".py")
        or path == "tests/test_turn_recall.py"
        or path.startswith("migrations/versions/")
        and path.endswith(".py")
    )


def nodes(text, names):
    tree = ast.parse(text)
    found = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    return [copy.deepcopy(found[name]) for name in names]


def module(header, body, commit):
    code = ast.unparse(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])))
    return (
        f"# Generated from Companion Core {commit}; see provenance/upstream.json.\n"
        "# SPDX-License-Identifier: MIT\n# ruff: noqa: E501\n" + header + "\n\n" + code + "\n"
    ).encode()


class ReviewInputs(ast.NodeTransformer):
    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name):
            replacement = {
                ("response", "text"): "text",
                ("self", "clock"): "clock",
                ("s", "audit"): "audit",
            }.get((node.value.id, node.attr))
            if replacement:
                return ast.copy_location(ast.Name(id=replacement, ctx=ast.Load()), node)
        return self.generic_visit(node)


def generated(sources, commit):
    contracts = sources["companion/contracts.py"].decode()
    work = sources["companion/memory_work.py"].decode()
    turns = sources["companion/turn_recall.py"].decode()
    extraction = nodes(
        work, ("short_refs", "from_refs", "repair_json", "parse_extraction", "_settled")
    )
    extraction[-1].name = "require_settled"
    rankings = ast.parse(turns)
    constants = [
        copy.deepcopy(node)
        for node in rankings.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(n, ast.Name) and n.id in {"_PUNCT", "_WEEKEND", "_WEEKDAY"}
            for n in node.targets
        )
    ]
    rank_body = constants + nodes(turns, ("_grams", "expand", "lexical", "_ranked", "merge"))
    rank_body += nodes(sources["companion/retrieval.py"].decode(), ("fuse",))
    prepare = nodes(work, ("prepare_memories",))[0]
    choices = [
        n
        for n in ast.walk(prepare)
        if isinstance(n, ast.Try)
        and any(isinstance(v, ast.Name) and v.id == "MemoryReview" for v in ast.walk(n))
    ]
    if len(choices) != 1:
        raise ValueError("UPSTREAM_REVIEW_STRUCTURE_CHANGED_REVIEW_EXPORTER")
    native_try = ReviewInputs().visit(copy.deepcopy(choices[0]))
    wrapper = ast.parse('''def resolve_review(text, candidates, catalog, *, repair_candidates=(),
                  audit=None, clock=None, request_id="reference-review"):
    """Apply native relation consistency checks to already source-validated candidates."""
    audit = audit or (lambda *args, **kwargs: None)
    clock = clock or (lambda: "")
    validation_reason = "schema"
    disagreements = []
''').body[0]
    wrapper.body.append(native_try)
    forbidden = {n.id for n in ast.walk(native_try) if isinstance(n, ast.Name)} & {
        "self",
        "s",
        "response",
    }
    if forbidden:
        raise ValueError("UPSTREAM_REVIEW_HOST_DEPENDENCY_CHANGED")
    prompt_tree = ast.parse(sources["companion/model.py"].decode())
    prompts = {}
    for n in prompt_tree.body:
        if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in {"EXTRACT_RULES", "REVIEW_RULES", "RECALL_RULES"}
            for t in n.targets
        ):
            name = next(t.id for t in n.targets if isinstance(t, ast.Name))
            prompts[f"prompts/{name.lower()}.txt"] = (ast.literal_eval(n.value) + "\n").encode()
    if len(prompts) != 3:
        raise ValueError("UPSTREAM_MEMORY_PROMPTS_CHANGED")
    return {
        "src/companion_memory/models.py": module(
            "from typing import Literal\nfrom pydantic import BaseModel, ConfigDict, Field",
            nodes(contracts, MODEL_CLASSES),
            commit,
        ),
        "src/companion_memory/extraction.py": module(
            "import json\nfrom .models import CoreError, Extraction", extraction, commit
        ),
        "src/companion_memory/ranking.py": module(
            "import math\nimport re\nfrom collections import Counter", rank_body, commit
        ),
        "src/companion_memory/review.py": module(
            "import json\nfrom .models import CoreError, MemoryReview",
            nodes(work, ("MemoryReviewError", "_repair_matches")) + [wrapper],
            commit,
        ),
        **prompts,
    }


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def verify(root=ROOT):
    record = json.loads((root / "provenance/upstream.json").read_bytes())
    sources = {}
    for name, entry in record["files"].items():
        data = (root / "reference/upstream" / name).read_bytes()
        if sha(data) != entry["sha256"]:
            raise ValueError("UPSTREAM_SNAPSHOT_DRIFT: " + name)
        sources[name] = data
    sources["companion/model.py"] = (root / "reference/prompt-source.py").read_bytes()
    if sha(sources["companion/model.py"]) != record["prompt_source"]["sha256"]:
        raise ValueError("PROMPT_SOURCE_DRIFT")
    for name, data in generated(sources, record["commit"]).items():
        if (root / name).read_bytes() != data:
            raise ValueError("GENERATED_REFERENCE_DRIFT: " + name)
    return {
        "status": "SOURCE_SNAPSHOT_AND_HELPERS_VERIFIED",
        "commit": record["commit"],
        "source_files": len(record["files"]),
    }


def sync(source, ref):
    commit = git(source, "rev-parse", ref + "^{commit}").decode().strip()
    tree = git(source, "rev-parse", commit + "^{tree}").decode().strip()
    paths = git(source, "ls-tree", "-r", "--name-only", commit).decode().splitlines()
    names = sorted(p for p in paths if selected(p))
    previous = ROOT / "provenance/upstream.json"
    if previous.exists():
        verify()
        old = json.loads(previous.read_bytes())
        for name in set(old["files"]) - set(names):
            target = (ROOT / "reference/upstream" / name).resolve()
            if not target.is_relative_to((ROOT / "reference/upstream").resolve()):
                raise ValueError("EXPORT_PATH_ESCAPE")
            target.unlink()
    sources, files = {}, {}
    for name in names:
        data = git(source, "show", commit + ":" + name)
        sources[name] = data
        write(ROOT / "reference/upstream" / name, data)
        files[name] = {
            "sha256": sha(data),
            "bytes": len(data),
            "blob": git(source, "rev-parse", commit + ":" + name).decode().strip(),
        }
    sources["companion/model.py"] = git(source, "show", commit + ":companion/model.py")
    # This read-only source exists to verify the three extracted memory prompt constants.
    write(ROOT / "reference/prompt-source.py", sources["companion/model.py"])
    for name, data in generated(sources, commit).items():
        write(ROOT / name, data)
    record = {
        "upstream": UPSTREAM,
        "commit": commit,
        "tree": tree,
        "source_ownership": "Companion Core",
        "publication_direction": "upstream-to-reference",
        "reference_license": "MIT",
        "files": files,
        "prompt_source": {
            "path": "companion/model.py",
            "sha256": sha(sources["companion/model.py"]),
        },
    }
    write(previous, (json.dumps(record, indent=2) + "\n").encode())
    return verify()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--ref")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        result = verify()
    else:
        if args.source is None or args.ref is None:
            parser.error("--source and --ref are required for an export")
        result = sync(args.source, args.ref)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
