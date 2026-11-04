"""Public-synthetic native Core memory evaluation; never imports grading material.

Historical assistant replies are supplied transcript fixtures, never regenerated.
Each exam uses a fresh native SDK conversation. Native source erasure after each
exam removes its inputs/outputs while retaining every paid-accounting liability.
This sequential isolation differs from upstream's per-question writable copies.
"""

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import secrets
import sys
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
WORKSPACE = BASE.parents[1]
CHECKOUT = WORKSPACE / ".local/worktrees/memory-benchmark-20261102"
UPSTREAM = BASE / "upstream"
sys.path.insert(0, str(CHECKOUT))

import httpx  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from companion import owner_authority, owner_input, paid_budget  # noqa: E402
from companion.config import PaidModelApproval, Settings  # noqa: E402
from companion.contracts import InboundEvent  # noqa: E402
from companion.core import Core  # noqa: E402
from companion.memory_work import checkpoint_state  # noqa: E402
from companion.model import ModelClient  # noqa: E402
from companion.owner_authority_protocol import (  # noqa: E402
    AuthorityChange,
    AuthorityPreview,
    OwnerCapture,
    OwnerGrantPolicy,
    OwnerRuntimeConfig,
)
from companion.qq_rich import input_digest  # noqa: E402
from companion.store import encode, migrate  # noqa: E402
from companion.transport import enqueue  # noqa: E402
from companion_delivery_protocol.authority import capture_signing_payload  # noqa: E402


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def append(path, value):
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(value, ensure_ascii=False) + "\n")
        out.flush()
        os.fsync(out.fileno())


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Clock:
    def __init__(self, value):
        self.set(value)

    def set(self, value):
        self.now = datetime.fromisoformat(value).astimezone(UTC)

    def __call__(self):
        return self.now.isoformat(timespec="microseconds")


def inputs():
    spec = importlib.util.spec_from_file_location(
        "public_exam_reader", UPSTREAM / "demo/read_exam.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    questions, histories = module.load()
    assert len(questions) == 108 and len(histories) == 1
    history = next(iter(histories.values()))[0]
    assert len(history) == 360
    return sorted(questions, key=lambda q: (q["now"], q["id"])), history


def settings(directory):
    original = tomllib.loads((WORKSPACE / "config.toml").read_text("utf-8"))
    env = {}
    for line in (WORKSPACE / ".env").read_text("utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip("\"'")
    model_key = os.getenv("COMPANION_MODEL_KEY") or env.get("COMPANION_MODEL_KEY", "")
    if not model_key:
        raise RuntimeError("MODEL_CREDENTIAL_UNAVAILABLE")
    values = {
        k: original[k]
        for k in (
            "provider",
            "model_url",
            "model_name",
            "max_output_tokens",
            "context_soft_tokens",
            "input_rate",
            "cached_input_rate",
            "output_rate",
            "extraction_min_events",
            "extraction_idle_seconds",
            "raw_event_retention_days",
        )
    }
    values.update(
        owner_qq_id="10001",
        bot_qq_id="10002",
        bridge_token=secrets.token_urlsafe(32),
        mode="live",
        model_key=model_key,
        database=str(directory / "core.sqlite3"),
        erasure_ledger=str(directory / "erasures.jsonl"),
        embedding_cache_dir=str(WORKSPACE / "data/embedding-cache"),
        owner_runtime=OwnerRuntimeConfig(mode="ENABLED"),
        memory_enabled=True,
        proactive_enabled=False,
        max_recent_messages=12,
        monthly_limit_micro_usd=1000000,
        memory_daily_micro_usd=1000000,
        autonomous_daily_micro_usd=1000000,
        operator_hot_reload=False,
    )
    auth = digest(
        {
            "user_request": "你参考别人的测试也对本项目进行一下记忆测试",
            "data": "Ornn8 public fictional demo only",
            "cap_micro_usd": 1000000,
        }
    )
    values["paid_model"] = PaidModelApproval(
        live_approved=True,
        window_id="public-memory-20261102-v1",
        approval_sha256=auth,
        provider=values["provider"],
        model=values["model_name"],
        endpoint=values["model_url"],
        currency="USD",
        timezone="Asia/Shanghai",
        starts_at="2026-01-01T00:00:00+08:00",
        expires_at="2026-11-03T00:00:00+08:00",
        rates_valid_until="2026-11-03T00:00:00+08:00",
        input_rate=values["input_rate"],
        cached_input_rate=values["cached_input_rate"],
        output_rate=values["output_rate"],
        max_input_tokens=40000,
        max_output_tokens=4096,
        per_attempt_micro_usd=20000,
        per_request_micro_usd=100000,
        per_request_calls=8,
        daily_micro_usd=1000000,
        daily_calls=1000,
        monthly_micro_usd=1000000,
        window_micro_usd=1000000,
        window_calls=1000,
        concurrency=1,
        journal_path=str(directory / "paid-budget.jsonl"),
    )
    return Settings(**values), auth


class Harness:
    def __init__(self, core, key, authority, directory):
        self.core, self.key, self.authority, self.directory = core, key, authority, directory
        self.phase, self.case, self.imported = "setup", None, 0
        self.turn_ids = set()

    def ingest(self, text, label, payload=None):
        core = self.core
        origin = "onebot-direct:FriendMessage:10001"
        number = (
            int(label.split("-")[-1])
            if label.startswith("turn-")
            else 100000 + int(digest(label)[:10], 16)
        )
        source = "10002:" + origin + ":epoch:public-memory-benchmark-v1:" + str(number)
        event_id = "evt_" + hashlib.sha256(source.encode()).hexdigest()
        at = core.clock()
        record = {
            "authority": self.authority,
            "kind": "authenticated_onebot_ws",
            "source_event_id": source,
            "event_id": event_id,
            "input_sha256": input_digest(payload or {"text": text}),
            "frame_sha256": digest({"synthetic_import": label, "text": text}),
            "evidence_sha256": digest(["PUBLIC_SYNTHETIC", label, at]),
            "identity_sha256": paid_budget.sha(["10001", "10002"]),
            "protocol_epoch": "public-memory-benchmark-v1",
            "occurred_at": at,
            "received_at": at,
        }
        record["signature"] = self.key.sign(capture_signing_payload(record)).hex()
        owner_input.approve(
            core.store, core.settings, core.clock, OwnerCapture.model_validate(record)
        )
        event = InboundEvent.model_validate(
            {
                "schema_version": 1,
                "event_id": event_id,
                "source": "qq.onebot",
                "source_event_id": source,
                "event_type": "message.received",
                "occurred_at": at,
                "conversation": {"platform_session_key": origin, "scope": "private"},
                "actor": {"platform_user_id": "10001", "role": "owner"},
                "payload": payload or {"text": text, "media": []},
                "trace_id": "bench_" + label,
            }
        )
        admitted = core.ingest(event, "public-memory:" + label)
        return admitted, event_id

    def import_turn(self, turn):
        admitted, event_id = self.ingest(turn["用户消息"], f"turn-{turn['轮次']:03}")
        s, at = self.core.store, self.core.clock()
        job = s.one(
            "SELECT j.*,e.conversation_id,e.body_json,e.trace_id FROM jobs j JOIN events e USING(event_id) WHERE job_id=?",
            (admitted["job_id"],),
        )
        # Fixture import: supplied assistant text is not a generated/provider/QQ receipt.
        with s.transaction():
            message = enqueue(s, event_id, job["conversation_id"], turn["助手回复"], at)
            s.execute(
                "UPDATE outbox SET state='SENT',sent_at=?,updated_at=? WHERE message_id=?",
                (at, at, message),
            )
            s.execute(
                "UPDATE jobs SET state='SUCCEEDED',updated_at=? WHERE job_id=?",
                (at, admitted["job_id"]),
            )
        self.turn_ids.add(event_id)
        self.imported += 1

    async def maintenance(self):
        self.phase, self.case = "maintenance", None
        core = self.core
        before = core.store.one("SELECT COUNT(*) n FROM model_usage")["n"]
        result = await core.extract_once()
        after = core.store.one("SELECT COUNT(*) n FROM model_usage")["n"]
        if after != before:
            checkpoint = checkpoint_state(core.store)
            record = {
                "now": core.clock(),
                "cutoff_turn": self.imported,
                "success": result,
                "new_calls": after - before,
                "checkpoint": checkpoint,
            }
            append(self.directory / "maintenance.jsonl", record)
            print(
                f"maintenance prefix={self.imported} calls={after - before} complete={result}",
                flush=True,
            )
            if any(row["state"] == "UNKNOWN" for row in core.store.rows("SELECT state FROM model_usage")):
                raise RuntimeError("NATIVE_MODEL_USAGE_UNKNOWN")

    def memory_fingerprint(self):
        s = self.core.store
        return digest(
            {
                table: s.rows(f"SELECT * FROM {table} ORDER BY rowid")
                for table in (
                    "memories",
                    "memory_evidence",
                    "episodes",
                    "episode_events",
                    "conversation_summaries",
                )
            }
        )

    async def exam(self, q):
        core, s = self.core, self.core.store
        self.phase, self.case = "exam", q["id"]
        assert self.imported == q["cutoff_turn"]
        # No future sources, and no prior exam can remain available to history/recall.
        active = s.rows(
            "SELECT event_id,source_event_id,occurred_at FROM events "
            "WHERE redacted=0 AND source='qq.onebot'"
        )
        assert all(row["event_id"] in self.turn_ids for row in active)
        assert all(row["occurred_at"] <= core.clock() for row in active)
        before_memory = self.memory_fingerprint()
        corpus_summaries = s.rows("SELECT * FROM conversation_summaries ORDER BY rowid")
        corpus_episodes = s.rows("SELECT * FROM episodes ORDER BY rowid")
        corpus_replies = s.rows("SELECT o.* FROM outbox o JOIN events e ON e.event_id=o.origin_event_id WHERE e.redacted=0 ORDER BY o.rowid")
        usage_before = {r["request_id"] for r in s.rows("SELECT request_id FROM model_usage")}
        admitted, event_id = self.ingest(q["question"], "exam-" + q["id"].replace("/", "-"))
        s.execute("UPDATE events SET memory_processed=1 WHERE event_id=?", (event_id,))
        job = s.one(
            "SELECT j.*,e.conversation_id,e.body_json,e.trace_id FROM jobs j JOIN events e USING(event_id) WHERE job_id=?",
            (admitted["job_id"],),
        )
        # Native history nomination, independently saved before any model answer.
        history = owner_input.history_sources(s, core.settings, core.clock, job)
        assert len(history) <= 6
        assert all(h["event_id"] in self.turn_ids for h in history)
        started = datetime.now(UTC)
        core.clock.now += timedelta(seconds=getattr(self, "advance_exam_seconds", 10))
        await core.run_once("public-memory-exam", job_id=admitted["job_id"])
        job = s.one(
            "SELECT j.*,e.conversation_id,e.body_json,e.trace_id FROM jobs j JOIN events e USING(event_id) WHERE job_id=?",
            (admitted["job_id"],),
        )
        parts = s.rows(
            "SELECT content_json,state FROM outbox WHERE origin_event_id=? ORDER BY rowid",
            (event_id,),
        )
        answer = "\n".join(json.loads(p["content_json"]).get("text", "") for p in parts)
        usages = [
            r for r in s.rows("SELECT * FROM model_usage") if r["request_id"] not in usage_before
        ]
        record = {
            **q,
            "status": job["state"],
            "error": job["last_error_code"],
            "answer": answer,
            "answer_stage": "native Outbox, no QQ transport",
            "actual_started_at": started.isoformat(),
            "actual_finished_at": datetime.now(UTC).isoformat(),
            "history_source_ids": [h["event_id"] for h in history],
            "short_term_turns": len(history),
            "memory_state_sha256": before_memory,
            "usage": usages,
            "event_id": event_id,
        }
        append(self.directory / "answers.jsonl", record)
        with s.transaction():
            core.ledger.expire_events(s, [event_id], core.clock())
            # Restore only the pre-exam fictional fixture summary snapshot. Native
            # erasure conservatively clears conversation-wide summaries. Money,
            # admission, erasure and audit rows always retain the actual exam.
            for reply in corpus_replies:
                assert reply["origin_event_id"] in self.turn_ids
                assert s.one("SELECT redacted FROM events WHERE event_id=?", (reply["origin_event_id"],))["redacted"] == 0
                s.execute("UPDATE outbox SET content_json=?,content_sha256=? WHERE message_id=?", (reply["content_json"], reply["content_sha256"], reply["message_id"]))
            for episode in corpus_episodes:
                assert not s.one("SELECT 1 FROM episode_events x JOIN events e USING(event_id) WHERE x.episode_id=? AND e.redacted=1", (episode["episode_id"],))
                s.execute("UPDATE episodes SET title=?,summary=?,status=? WHERE episode_id=?", (episode["title"], episode["summary"], episode["status"], episode["episode_id"]))
            for summary in corpus_summaries:
                assert all(s.one("SELECT redacted FROM events WHERE event_id=?", (summary[k],))["redacted"] == 0 for k in ("first_event_id", "last_event_id"))
                if not s.one("SELECT 1 FROM conversation_summaries WHERE summary_id=?", (summary["summary_id"],)):
                    s.insert("conversation_summaries", **summary)
        assert self.memory_fingerprint() == before_memory, "EXAM_CHANGED_PERSISTENT_MEMORY"
        assert s.one("SELECT redacted FROM events WHERE event_id=?", (event_id,))["redacted"] == 1
        append(
            self.directory / "isolation.jsonl",
            {
                "id": q["id"],
                "erased": True,
                "memory_unchanged": True,
                "budget_usage_retained": all(
                    s.one("SELECT 1 FROM model_usage WHERE request_id=?", (u["request_id"],))
                    for u in usages
                ),
            },
        )
        print(
            f"exam {q['id']} prefix={self.imported} state={job['state']} calls={len(usages)}",
            flush=True,
        )
        return record


async def run(directory, limit):  # noqa: ASYNC240 -- workspace-only synchronous setup
    questions, history = inputs()
    directory.mkdir(parents=True, exist_ok=False)
    cfg, auth = settings(directory)
    clock = Clock(history[0]["逻辑时间"])
    manifest = {
        "classification": "PUBLIC_SYNTHETIC_DEMO",
        "core_commit": "3da60d63307612ae813b8e6fd61ca318eedd4140",
        "benchmark_commit": "4c9d147ec650419cdd3e66d81d15582e4672fe3b",
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),  # noqa: ASYNC240
        "history_sha256": questions[0]["history_sha256"],
        "question_file_sha256": hashlib.sha256(
            (UPSTREAM / "demo/exam-inputs.jsonl").read_bytes()
        ).hexdigest(),
        "questions": limit or len(questions),
        "short_term_turns": 6,
        "model": cfg.model_name,
        "chat_thinking": cfg.chat_thinking,
        "max_output_tokens": cfg.max_output_tokens,
        "context_soft_tokens": cfg.context_soft_tokens,
        "extraction_min_events": cfg.extraction_min_events,
        "extraction_idle_seconds": cfg.extraction_idle_seconds,
        "retention_days": cfg.raw_event_retention_days,
        "budget_cap_micro_usd": 1000000,
        "rates": {k: getattr(cfg, k) for k in ("input_rate", "cached_input_rate", "output_rate")},
        "isolation": (
            "fresh per-job native SDK conversation; native source erasure; retained accounting"
        ),
        "deviations": [
            "sequential native erasure isolation rather than independent writable DB copies",
            "extractor consumes owner messages; assistant fixtures enter recent dialogue only",
        ],
        "authorization_sha256": auth,
        "actual_started_at": datetime.now(UTC).isoformat(),
        "status": "PREPARED_NO_MODEL_CALLS",
    }
    save(directory / "manifest.json", manifest)
    migrate(cfg.database)
    holder = {}

    async def observe_request(request):
        h = holder.get("h")
        append(
            directory / "requests.jsonl",
            {
                "phase": h.phase if h else "setup",
                "case": h.case if h else None,
                "actual_at": datetime.now(UTC).isoformat(),
                "logical_at": clock(),
                "payload": json.loads(request.content),
            },
        )

    async def observe_response(response):
        await response.aread()
        h = holder.get("h")
        value = response.json()
        append(
            directory / "responses.jsonl",
            {
                "phase": h.phase if h else "setup",
                "case": h.case if h else None,
                "http_status": response.status_code,
                "actual_at": datetime.now(UTC).isoformat(),
                "response": value,
            },
        )

    async with httpx.AsyncClient(
        timeout=cfg.timeout_seconds,
        trust_env=False,
        event_hooks={"request": [observe_request], "response": [observe_response]},
    ) as client:
        with Core(cfg, ModelClient(cfg, client), clock) as core:
            key = Ed25519PrivateKey.generate()
            policy = OwnerGrantPolicy(
                owner_qq_id="10001",
                purposes=["chat", "memory", "history"],
                authorization_sha256=auth,
                paid_contract_sha256=paid_budget.sha(paid_budget.snapshot(cfg)),
                memory_scope="owner_private",
                history={
                    "scope": "owner_private",
                    "not_before": "2026-01-01T00:00:00+08:00",
                    "max_turns": 6,
                    "max_utf8_bytes": 16000,
                },
                capture={
                    "public_key": key.public_key().public_bytes_raw().hex(),
                    "identity_sha256": paid_budget.sha(["10001", "10002"]),
                    "protocol_epoch": "public-memory-benchmark-v1",
                },
            )
            query = AuthorityPreview(expected_revision=0, policy=policy)
            preview = owner_authority.preview(core.store, cfg, clock, query)
            authority = owner_authority.activate(
                core.store,
                cfg,
                clock,
                AuthorityChange(
                    operation_id="public-memory-benchmark-activate",
                    **query.model_dump(),
                    preview_sha256=preview["preview_sha256"],
                ),
            )["authority"]
            h = Harness(core, key, authority, directory)
            holder["h"] = h
            try:
                for q in questions[: limit or None]:
                    while h.imported < q["cutoff_turn"]:
                        turn = history[h.imported]
                        clock.set(turn["逻辑时间"])
                        await h.maintenance()
                        h.import_turn(turn)
                    clock.set(q["now"])
                    await h.maintenance()
                    await h.exam(q)
                manifest["status"] = "COMPLETED"
            except Exception as error:
                manifest.update(
                    status="INTERRUPTED",
                    error_type=type(error).__name__,
                    error_code=getattr(error, "code", str(error)),
                    phase=h.phase,
                    case=h.case,
                )
                print(
                    "interrupted",
                    type(error).__name__,
                    getattr(error, "code", str(error)),
                    flush=True,
                )
            finally:
                manifest.update(
                    actual_finished_at=datetime.now(UTC).isoformat(),
                    imported_turns=h.imported,
                    usage=core.store.rows(
                        "SELECT scenario,state,COUNT(*) calls, SUM(input_tokens) input_tokens,"
                        "SUM(output_tokens) output_tokens,SUM(cached_input_tokens) cached_tokens,"
                        "SUM(billed_micro_usd) billed_micro_usd FROM model_usage "
                        "GROUP BY scenario,state"
                    ),
                )
                save(directory / "manifest.json", manifest)
    print(
        json.dumps(
            {k: manifest.get(k) for k in ("status", "phase", "case", "error_code", "usage")},
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if not args.name.replace("-", "").isalnum():
        raise ValueError("invalid run name")
    asyncio.run(run(BASE / args.name, args.limit))
