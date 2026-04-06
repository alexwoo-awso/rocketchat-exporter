from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rocketchat_exporter.models import ExportOptions, Filters
from rocketchat_exporter.service import RocketChatExportService


def build_options() -> ExportOptions:
    return ExportOptions(
        mongo_uri="mongodb://example",
        database_name="rocketchat",
        format="json",
        mode="full",
        output_path=Path("out.json"),
        filters=Filters(),
        smart_context=True,
    )


class FakeCursor:
    def __init__(self, docs: list[dict[str, object]]) -> None:
        self.docs = docs

    def __iter__(self):
        return iter(self.docs)

    def sort(self, key: str, direction: int) -> list[dict[str, object]]:
        reverse = direction == -1
        return sorted(self.docs, key=lambda item: item.get(key), reverse=reverse)


class FakeCollection:
    def __init__(self, docs: list[dict[str, object]]) -> None:
        self.docs = docs

    def find(
        self,
        query: dict[str, object] | None = None,
        projection: dict[str, int] | None = None,
    ) -> FakeCursor:
        matched = [doc for doc in self.docs if self._matches(doc, query or {})]
        if projection:
            trimmed = []
            for doc in matched:
                item = {}
                for key in projection:
                    if key in doc:
                        item[key] = doc[key]
                trimmed.append(item)
            return FakeCursor(trimmed)
        return FakeCursor(matched)

    def _matches(self, doc: dict[str, object], query: dict[str, object]) -> bool:
        for key, value in query.items():
            if key == "$or":
                return any(self._matches(doc, clause) for clause in value)
            if key == "$and":
                return all(self._matches(doc, clause) for clause in value)
            current = self._dig(doc, key)
            if isinstance(value, dict):
                if "$in" in value and current not in value["$in"]:
                    return False
                if "$gte" in value and current < value["$gte"]:
                    return False
                if "$lte" in value and current > value["$lte"]:
                    return False
                if "$lt" in value and current >= value["$lt"]:
                    return False
                continue
            if current != value:
                return False
        return True

    def _dig(self, doc: dict[str, object], dotted_key: str) -> object:
        current: object = doc
        for part in dotted_key.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current


class ServiceQueryTests(unittest.TestCase):
    def test_unresolved_room_name_returns_empty_query(self) -> None:
        options = build_options()
        options.filters.room_names = {"missing"}
        service = RocketChatExportService(options)

        query = service._build_direct_query({"room-1": {"name": "general"}})

        self.assertEqual(query, {"rid": {"$in": []}})

    def test_collect_messages_adds_context_messages(self) -> None:
        options = build_options()
        options.filters.usernames = {"alice"}
        options.filters.room_ids = {"room-1"}

        root = {
            "_id": "m1",
            "rid": "room-1",
            "msg": "Root",
            "u": {"_id": "u2", "username": "bob", "name": "Bob"},
            "ts": datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
            "_updatedAt": datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
            "tcount": 1,
        }
        reply = {
            "_id": "m2",
            "rid": "room-1",
            "msg": "Reply from Alice",
            "u": {"_id": "u1", "username": "alice", "name": "Alice"},
            "ts": datetime(2026, 4, 1, 12, 1, tzinfo=UTC),
            "_updatedAt": datetime(2026, 4, 1, 12, 1, tzinfo=UTC),
            "tmid": "m1",
        }
        other_reply = {
            "_id": "m3",
            "rid": "room-1",
            "msg": "Follow-up",
            "u": {"_id": "u3", "username": "charlie", "name": "Charlie"},
            "ts": datetime(2026, 4, 1, 12, 2, tzinfo=UTC),
            "_updatedAt": datetime(2026, 4, 1, 12, 2, tzinfo=UTC),
            "tmid": "m1",
        }

        class TestService(RocketChatExportService):
            def _build_client(self) -> object:
                class FakeDatabase:
                    def __getitem__(self, name: str) -> FakeCollection:
                        if name == "rocketchat_message":
                            return FakeCollection([root, reply, other_reply])
                        return FakeCollection(
                            [{"_id": "room-1", "name": "general", "fname": "General", "t": "c"}]
                        )

                class FakeClient:
                    def __getitem__(self, name: str) -> FakeDatabase:
                        return FakeDatabase()

                    def close(self) -> None:
                        return None

                return FakeClient()

        service = TestService(options)
        messages, summary = service.collect_messages()

        self.assertEqual([message["message_id"] for message in messages], ["m1", "m2", "m3"])
        self.assertEqual(messages[0]["context_reason"], "original-of-direct-reply")
        self.assertEqual(messages[1]["context_reason"], "direct-match")
        self.assertEqual(messages[2]["context_reason"], "thread-context")
        self.assertEqual(summary["message_count"], 3)
        self.assertEqual(summary["direct_match_count"], 1)


if __name__ == "__main__":
    unittest.main()
