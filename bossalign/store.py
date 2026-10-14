"""SQLite persistence for feedback events, current rules, and rule history."""

import json
import sqlite3
import threading
from pathlib import Path
from typing import List, Optional

from .schema import BoundaryRule, FeedbackEvent


class MemoryStore:
    _instances = set()

    def __init__(self, path):
        self.path = str(path) if str(path) == ":memory:" else str(Path(path).expanduser())
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        with self._lock:
            MemoryStore._instances.add(self)
        self._initialize()

    @classmethod
    def close_all(cls) -> None:
        stores = list(cls._instances)
        cls._instances.clear()
        for store in stores:
            try:
                store.close()
            except Exception:
                pass
        import gc
        gc.collect()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL,
                    description TEXT NOT NULL
                );
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
                CREATE TABLE IF NOT EXISTS event_audit_log (
                    audit_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    reason TEXT,
                    snapshot_json TEXT NOT NULL
                );
                """
            )
            self._run_migrations()

    def _run_migrations(self) -> None:
        # Check columns for feedback_events
        cur = self._connection.execute("PRAGMA table_info(feedback_events)")
        event_cols = {row["name"] for row in cur.fetchall()}
        if "preference_owner" not in event_cols:
            self._connection.execute("ALTER TABLE feedback_events ADD COLUMN preference_owner TEXT")
        if "status" not in event_cols:
            self._connection.execute("ALTER TABLE feedback_events ADD COLUMN status TEXT DEFAULT 'recorded'")
        if "occurred_at" not in event_cols:
            self._connection.execute("ALTER TABLE feedback_events ADD COLUMN occurred_at TEXT")
        if "parent_event_id" not in event_cols:
            self._connection.execute("ALTER TABLE feedback_events ADD COLUMN parent_event_id TEXT")
        if "derived_rule_id" not in event_cols:
            self._connection.execute("ALTER TABLE feedback_events ADD COLUMN derived_rule_id TEXT")

        # Check columns for rules
        cur = self._connection.execute("PRAGMA table_info(rules)")
        rule_cols = {row["name"] for row in cur.fetchall()}
        if "preference_owner" not in rule_cols:
            self._connection.execute("ALTER TABLE rules ADD COLUMN preference_owner TEXT")
        if "conflict_key" not in rule_cols:
            self._connection.execute("ALTER TABLE rules ADD COLUMN conflict_key TEXT")
        if "domain" not in rule_cols:
            self._connection.execute("ALTER TABLE rules ADD COLUMN domain TEXT")

        # Create indices
        self._connection.execute("CREATE INDEX IF NOT EXISTS idx_events_owner ON feedback_events(preference_owner)")
        self._connection.execute("CREATE INDEX IF NOT EXISTS idx_events_parent ON feedback_events(parent_event_id)")
        self._connection.execute("CREATE INDEX IF NOT EXISTS idx_rules_conflict_key ON rules(conflict_key)")

        # Record migration
        cur = self._connection.execute("SELECT 1 FROM schema_migrations WHERE version = 2")
        if cur.fetchone() is None:
            import datetime
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self._connection.execute(
                "INSERT INTO schema_migrations(version, applied_at, description) VALUES (?, ?, ?)",
                (2, now, "V0.2 Event Store, Schema Versioning and Audit Log"),
            )

    @staticmethod
    def _json(value) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def save_event(self, event: FeedbackEvent) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO feedback_events(event_id, reviewer, created_at, preference_owner, status, occurred_at, parent_event_id, derived_rule_id, data_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.event_id,
                    event.reviewer,
                    getattr(event, "recorded_at", None) or event.timestamp,
                    event.preference_owner,
                    getattr(event, "status", "recorded"),
                    event.timestamp,
                    getattr(event, "parent_event_id", None),
                    event.derived_rule_id,
                    self._json(event.to_dict()),
                ),
            )

    def save_feedback(self, event: FeedbackEvent, rule: BoundaryRule) -> None:
        with self._lock, self._connection:
            self.save_event(event)
            self._insert_rule(rule)

    def get_event(self, event_id: str) -> Optional[FeedbackEvent]:
        with self._lock:
            row = self._connection.execute("SELECT data_json FROM feedback_events WHERE event_id = ?", (event_id,)).fetchone()
        return FeedbackEvent.from_dict(json.loads(row["data_json"])) if row else None

    def revoke_event(self, event_id: str, revoked_by: str, reason: str = "") -> bool:
        with self._lock, self._connection:
            event = self.get_event(event_id)
            if not event:
                return False
            import uuid, datetime
            event.status = "revoked"
            snapshot = self._json(event.to_dict())
            self._connection.execute(
                "UPDATE feedback_events SET status = 'revoked', data_json = ? WHERE event_id = ?",
                (snapshot, event_id),
            )
            audit_id = "aud_" + uuid.uuid4().hex
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self._connection.execute(
                "INSERT INTO event_audit_log(audit_id, event_id, action, actor, timestamp, reason, snapshot_json) "
                "VALUES (?, ?, 'revoke', ?, ?, ?, ?)",
                (audit_id, event_id, revoked_by, now, reason, snapshot),
            )
            return True

    def get_rule_evidence_chain(self, rule_id: str) -> List[FeedbackEvent]:
        """Trace a rule back through its source events and parent causal links."""
        rule = self.get_rule(rule_id)
        if not rule:
            return []
        visited = set()
        queue = list(rule.source_event_ids or [])
        events: List[FeedbackEvent] = []
        while queue:
            eid = queue.pop(0)
            if eid in visited:
                continue
            visited.add(eid)
            evt = self.get_event(eid)
            if evt:
                events.append(evt)
                if getattr(evt, "parent_event_id", None) and evt.parent_event_id not in visited:
                    queue.append(evt.parent_event_id)
                for linked in getattr(evt, "linked_event_ids", []):
                    if linked not in visited:
                        queue.append(linked)
        return events

    def save_rule(self, rule: BoundaryRule) -> None:
        with self._lock, self._connection:
            self._insert_rule(rule)

    def _insert_rule(self, rule: BoundaryRule) -> None:
        project = rule.applicable_scope.get("project") if isinstance(rule.applicable_scope, dict) else None
        snapshot = self._json(rule.to_dict())
        self._connection.execute(
            "INSERT INTO rules(rule_id, reviewer, project, status, created_at, updated_at, version, preference_owner, conflict_key, domain, data_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                rule.rule_id,
                rule.reviewer,
                project,
                rule.status.value,
                rule.created_at,
                rule.updated_at,
                rule.version,
                rule.preference_owner,
                rule.conflict_key,
                getattr(rule, "domain", None),
                snapshot,
            ),
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
            query += " WHERE status NOT IN ('inactive', 'rejected', 'revoked', 'superseded', 'expired')"
        query += " ORDER BY created_at, rule_id"
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [BoundaryRule.from_dict(json.loads(row["data_json"])) for row in rows]

    def list_rules(
        self,
        reviewer: Optional[str] = None,
        project: Optional[str] = None,
        preference_owner: Optional[str] = None,
        status: Optional[str] = None,
        include_inactive: bool = True,
    ) -> List[BoundaryRule]:
        rules = self.all_rules(include_inactive=include_inactive)
        return [
            rule for rule in rules
            if (reviewer is None or rule.reviewer == reviewer)
            and (preference_owner is None or rule.preference_owner == preference_owner)
            and (status is None or rule.status.value == str(status) or rule.status == status)
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
                "UPDATE rules SET reviewer = ?, project = ?, status = ?, updated_at = ?, version = ?, preference_owner = ?, conflict_key = ?, domain = ?, data_json = ? "
                "WHERE rule_id = ? AND version = ?",
                (
                    rule.reviewer,
                    project,
                    rule.status.value,
                    rule.updated_at,
                    rule.version,
                    rule.preference_owner,
                    rule.conflict_key,
                    getattr(rule, "domain", None),
                    snapshot,
                    rule.rule_id,
                    current["version"],
                ),
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

    def delete_rule(self, rule_id: str, source_event_ids=()) -> bool:
        """Delete a rule, its history, and the source events owned by that rule."""
        with self._lock, self._connection:
            current = self._connection.execute(
                "SELECT 1 FROM rules WHERE rule_id = ?", (rule_id,)
            ).fetchone()
            if current is None:
                return False
            event_ids = list(dict.fromkeys(source_event_ids or ()))
            if event_ids:
                placeholders = ",".join("?" for _ in event_ids)
                self._connection.execute(
                    "DELETE FROM feedback_events WHERE event_id IN (%s)" % placeholders,
                    event_ids,
                )
            self._connection.execute("DELETE FROM rule_versions WHERE rule_id = ?", (rule_id,))
            self._connection.execute("DELETE FROM rules WHERE rule_id = ?", (rule_id,))
            return True

    def feedback_events(
        self,
        reviewer: Optional[str] = None,
        preference_owner: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[FeedbackEvent]:
        query = "SELECT data_json FROM feedback_events"
        clauses = []
        params = []
        if reviewer is not None:
            clauses.append("reviewer = ?")
            params.append(reviewer)
        if preference_owner is not None:
            clauses.append("preference_owner = ?")
            params.append(preference_owner)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at, event_id"
        with self._lock:
            rows = self._connection.execute(query, tuple(params)).fetchall()
        return [FeedbackEvent.from_dict(json.loads(row["data_json"])) for row in rows]

    def close(self) -> None:
        with self._lock:
            if hasattr(self, "_connection") and self._connection is not None:
                try:
                    self._connection.close()
                except Exception:
                    pass
                self._connection = None
            MemoryStore._instances.discard(self)

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
