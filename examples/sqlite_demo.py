"""Offline, single-fact teaching example using the published native helpers."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from companion_memory import lexical, parse_extraction, require_settled, resolve_review


class ExampleStore:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, text TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS model_usage(
                request_id TEXT PRIMARY KEY, state TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS facts(
                id TEXT PRIMARY KEY, content TEXT NOT NULL,
                event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE);
        """)

    def one(self, sql, params):
        return self.db.execute(sql, params).fetchone()

    def remember(self, candidate, review_text, request_id):
        """Only initial owner facts: production source handles updates and permission replay."""
        with self.db:
            require_settled(self, request_id)
            event = self.one("SELECT text FROM events WHERE id=?", (candidate.evidence_event_id,))
            if (
                not event
                or candidate.evidence_quote not in event["text"]
                or candidate.speaker != "owner"
                or candidate.evidence_reference_id
                or candidate.update
            ):
                raise ValueError("EXAMPLE_REQUIRES_INITIAL_OWNER_FACT_AND_EXACT_SOURCE")
            supported, relations = resolve_review(review_text, [candidate], {})
            if not supported or any(relations[0].values()):
                raise ValueError("EXAMPLE_REQUIRES_SUPPORTED_NEW_FACT")
            self.db.execute(
                "INSERT INTO facts VALUES(?,?,?)",
                (candidate.fact_key, candidate.content, candidate.evidence_event_id),
            )

    def recall(self, query):
        rows = list(self.db.execute("SELECT * FROM facts ORDER BY id"))
        scores = lexical(query, [row["content"] for row in rows])
        return [
            dict(rows[i])
            for i in sorted(range(len(rows)), key=lambda i: -scores[i])
            if scores[i] > 0
        ]

    def erase_source(self, event_id):
        with self.db:
            self.db.execute("DELETE FROM events WHERE id=?", (event_id,))

    def close(self):
        self.db.close()


def run(path):
    store = ExampleStore(path)
    try:
        text = "我周末喜欢去植物园散步。"
        with store.db:
            store.db.execute("INSERT INTO events VALUES(?,?)", ("fictional-event", text))
            store.db.execute("INSERT INTO model_usage VALUES(?,?)", ("offline-fixture", "SETTLED"))
        # Fixed model-output fixtures: this example never calls a provider.
        extraction, _ = parse_extraction(
            json.dumps(
                {
                    "memories": [
                        {
                            "subject": "user",
                            "kind": "preference",
                            "fact_key": "weekend-walk",
                            "content": "周末喜欢去植物园散步",
                            "evidence_event_id": "e0",
                            "evidence_quote": text,
                            "speaker": "owner",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            {"e0": "fictional-event"},
        )
        review = json.dumps(
            {
                "relations": [
                    {
                        "supported": True,
                        "update_authorized": False,
                        "claims_replacement": False,
                        "replaces": [],
                    }
                ]
            }
        )
        store.remember(extraction.memories[0], review, "offline-fixture")
        before = store.recall("周末去哪里散步")
        assert len(before) == 1 and before[0]["event_id"] == "fictional-event"
        store.erase_source("fictional-event")
        after = store.recall("周末去哪里散步")
        assert after == []
        return {"remembered": before, "after_source_erasure": after, "provider_calls": 0}
    finally:
        store.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", type=Path, help="New SQLite file; defaults to in-memory SQLite"
    )
    args = parser.parse_args()
    print(json.dumps(run(args.database or ":memory:"), ensure_ascii=False, indent=2))
