"""SQLite persistence for feedback events, current rules, and rule history."""

import json
import sqlite3
import threading
from pathlib import Path
from typing import List, Optional

from .schema import BoundaryRule, FeedbackEvent


class MemoryStore:
    def __init__(self, path):
        self.path = str(path) if str(path) == ":memory:" else str(Path(path).expanduser())
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS feedback_events (
                    event_id TEXT PRIMARY KEY,
                    reviewer TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    data_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS rules (
                    rule_id TEXT PRIMARY KEY,
                    reviewer TEXT NOT NULL,
                    project TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    data_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_rules_reviewer_project
                    ON rules(reviewer, project, status);
                CREATE TABLE IF NOT EXISTS rule_versions (
                    rule_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    changed_at TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    PRIMARY KEY (rule_id, version),
                    FOREIGN KEY (rule_id) REFERENCES rules(rule_id)
                );
                """
            )

    @staticmethod
    def _json(value) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def save_feedback(self, event: FeedbackEvent, rule: BoundaryRule) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO feedback_events(event_id, reviewer, created_at, data_json) VALUES (?, ?, ?, ?)",
                (event.event_id, event.reviewer, event.timestamp, self._json(event.to_dict())),
            )
            self._insert_rule(rule)

    def save_rule(self, rule: BoundaryRule) -> None:
        with self._lock, self._connection:
            self._insert_rule(rule)

    def _insert_rule(self, rule: BoundaryRule) -> None:
        project = rule.applicable_scope.get("project") if isinstance(rule.applicable_scope, dict) else None
        snapshot = self._json(rule.to_dict())
        self._connection.execute(
            "INSERT INTO rules(rule_id, reviewer, project, status, created_at, updated_at, version, data_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (rule.rule_id, rule.reviewer, project, rule.status.value, rule.created_at, rule.updated_at, rule.version, snapshot),
        )
        self._connection.execute(
            "INSERT INTO rule_versions(rule_id, version, changed_at, snapshot_json) VALUES (?, ?, ?, ?)",
            (rule.rule_id, rule.version, rule.updated_at, snapshot),
        )

    def get_rule(self, rule_id: str) -> Optional[BoundaryRule]:
        with self._lock:
            row = self._connection.execute("SELECT data_json FROM rules WHERE rule_id = ?", (rule_id,)).fetchone()
        return BoundaryRule.from_dict(json.loads(row["data_json"])) if row else None

    def all_rules(self, include_inactive: bool = True) -> List[BoundaryRule]:
        query = "SELECT data_json FROM rules"
        params = ()
        if not include_inactive:
            query += " WHERE status != ?"
            params = ("inactive",)
        query += " ORDER BY created_at, rule_id"
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [BoundaryRule.from_dict(json.loads(row["data_json"])) for row in rows]

    def list_rules(
        self,
        reviewer: Optional[str] = None,
        project: Optional[str] = None,
        include_inactive: bool = True,
    ) -> List[BoundaryRule]:
        rules = self.all_rules(include_inactive=include_inactive)
        return [
            rule for rule in rules
            if (reviewer is None or rule.reviewer == reviewer)
            and (
                project is None
                or rule.applicable_scope.get("project") in (None, project)
            )
        ]

    def update_rule(self, rule: BoundaryRule) -> None:
        project = rule.applicable_scope.get("project") if isinstance(rule.applicable_scope, dict) else None
        snapshot = self._json(rule.to_dict())
        with self._lock, self._connection:
            current = self._connection.execute(
                "SELECT version FROM rules WHERE rule_id = ?", (rule.rule_id,)
            ).fetchone()
            if current is None:
                raise KeyError("Unknown rule: %s" % rule.rule_id)
            if rule.version != current["version"] + 1:
                raise ValueError("Rule version changed; reload the rule before updating")
            cursor = self._connection.execute(
                "UPDATE rules SET reviewer = ?, project = ?, status = ?, updated_at = ?, version = ?, data_json = ? "
                "WHERE rule_id = ? AND version = ?",
                (rule.reviewer, project, rule.status.value, rule.updated_at, rule.version, snapshot, rule.rule_id, current["version"]),
            )
            if cursor.rowcount != 1:
                raise ValueError("Rule version changed; reload the rule before updating")
            self._connection.execute(
                "INSERT INTO rule_versions(rule_id, version, changed_at, snapshot_json) VALUES (?, ?, ?, ?)",
                (rule.rule_id, rule.version, rule.updated_at, snapshot),
            )

    def rule_versions(self, rule_id: str):
        with self._lock:
            rows = self._connection.execute(
                "SELECT snapshot_json FROM rule_versions WHERE rule_id = ? ORDER BY version", (rule_id,)
            ).fetchall()
        return [json.loads(row["snapshot_json"]) for row in rows]

    def feedback_events(self, reviewer: Optional[str] = None) -> List[FeedbackEvent]:
        if reviewer is None:
            query, params = "SELECT data_json FROM feedback_events ORDER BY created_at, event_id", ()
        else:
            query, params = (
                "SELECT data_json FROM feedback_events WHERE reviewer = ? ORDER BY created_at, event_id",
                (reviewer,),
            )
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [FeedbackEvent.from_dict(json.loads(row["data_json"])) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
