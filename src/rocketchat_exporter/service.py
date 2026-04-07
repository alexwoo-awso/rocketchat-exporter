from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from rocketchat_exporter.models import ExportOptions
from rocketchat_exporter.utils import serialize_datetime


MESSAGE_COLLECTION = "rocketchat_message"
ROOM_COLLECTION = "rocketchat_room"


class RocketChatExportService:
    def __init__(self, options: ExportOptions) -> None:
        self.options = options

    def collect_messages(self) -> tuple[list[dict[str, object]], dict[str, object]]:
        client = self._build_client()
        try:
            db = client[self.options.database_name]
            messages_collection = db[MESSAGE_COLLECTION]
            room_map = self._build_room_map(db[ROOM_COLLECTION])

            direct_messages = self._find_direct_messages(messages_collection, room_map)
            direct_ids = {message["_id"] for message in direct_messages}
            message_map = {message["_id"]: message for message in direct_messages}

            if self.options.smart_context and direct_messages:
                context_messages = self._find_context_messages(
                    collection=messages_collection,
                    direct_messages=direct_messages,
                    known_ids=direct_ids,
                    room_map=room_map,
                )
                message_map.update(context_messages)

            normalized_messages = [
                self._normalize_message(message_map[key], room_map=room_map)
                for key in sorted(message_map, key=lambda item: self._sort_key(message_map[item]))
            ]
            summary = self._build_summary(
                normalized_messages,
                direct_count=len(direct_messages),
            )
            return normalized_messages, summary
        finally:
            client.close()

    def _build_client(self) -> Any:
        try:
            from pymongo import MongoClient
        except ImportError as exc:
            raise RuntimeError(
                "pymongo is required. Install dependencies before running the exporter."
            ) from exc
        return MongoClient(self.options.mongo_uri)

    def _build_room_map(self, collection: Any) -> dict[str, dict[str, Any]]:
        room_map: dict[str, dict[str, Any]] = {}
        for room in collection.find({}, {"_id": 1, "name": 1, "fname": 1, "t": 1}):
            room_id = str(room["_id"])
            room_map[room_id] = room
        return room_map

    def _find_direct_messages(
        self,
        collection: Any,
        room_map: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        query = self._build_direct_query(room_map)
        return list(collection.find(query).sort("ts", 1))

    def _build_direct_query(self, room_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
        filters = self.options.filters
        query: dict[str, Any] = {}

        room_ids = set(filters.room_ids)
        matched_room_ids: set[str] = set()
        if filters.room_names:
            matched_room_ids = self._resolve_room_ids(room_map, filters.room_names)
            room_ids.update(matched_room_ids)
        if filters.room_names and not matched_room_ids and not filters.room_ids:
            return {"rid": {"$in": []}}

        excluded_room_ids = set(filters.excluded_room_ids)
        if filters.excluded_room_names:
            excluded_room_ids.update(
                self._resolve_room_ids(room_map, filters.excluded_room_names)
            )

        room_query = self._build_room_query(
            included_room_ids=room_ids,
            excluded_room_ids=excluded_room_ids,
        )
        if room_query is not None:
            query["rid"] = room_query

        user_clauses: list[dict[str, Any]] = []
        if filters.user_ids:
            user_clauses.append({"u._id": {"$in": sorted(filters.user_ids)}})
        if filters.usernames:
            user_clauses.append({"u.username": {"$in": sorted(filters.usernames)}})
        if user_clauses:
            query["$or"] = user_clauses

        ts_clauses: list[dict[str, Any]] = []
        if filters.date_from or filters.date_to:
            ts_range: dict[str, Any] = {}
            if filters.date_from:
                ts_range["$gte"] = filters.date_from
            if filters.date_to:
                ts_range["$lte"] = filters.date_to
            ts_clauses.append({"ts": ts_range})

        if filters.dates:
            date_specific = []
            for dt in sorted(filters.dates):
                day_start = dt.astimezone(UTC).replace(
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                date_specific.append(
                    {
                        "ts": {
                            "$gte": day_start,
                            "$lt": day_start + timedelta(days=1),
                        }
                    }
                )
            ts_clauses.append({"$or": date_specific})

        if len(ts_clauses) == 1:
            query.update(ts_clauses[0])
        elif ts_clauses:
            query["$and"] = ts_clauses

        return query

    def _resolve_room_ids(
        self,
        room_map: dict[str, dict[str, Any]],
        expected_names: set[str],
    ) -> set[str]:
        matched_ids = set()
        for room_id, room in room_map.items():
            if room.get("name") in expected_names or room.get("fname") in expected_names:
                matched_ids.add(room_id)
        return matched_ids

    def _find_context_messages(
        self,
        *,
        collection: Any,
        direct_messages: list[dict[str, Any]],
        known_ids: set[str],
        room_map: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        context_messages: dict[str, dict[str, Any]] = {}
        room_query = self._build_context_room_query(room_map)
        thread_ids = {message.get("tmid") for message in direct_messages if message.get("tmid")}
        if self.options.filters.include_replies:
            thread_ids.update(
                message["_id"]
                for message in direct_messages
                if self._message_starts_thread(message)
            )
        if thread_ids:
            query: dict[str, Any] = {"tmid": {"$in": sorted(thread_ids)}}
            if room_query is not None:
                query["rid"] = room_query
            for message in collection.find(query):
                message_id = str(message["_id"])
                if message_id in known_ids:
                    continue
                context_messages[message_id] = message

        if self.options.filters.include_originals:
            original_ids = {
                str(message["tmid"])
                for message in direct_messages
                if message.get("tmid")
            }
            if original_ids:
                query = {"_id": {"$in": sorted(original_ids)}}
                if room_query is not None:
                    query["rid"] = room_query
                for message in collection.find(query):
                    message_id = str(message["_id"])
                    if message_id in known_ids:
                        continue
                    context_messages[message_id] = message

        self._apply_context_reasons(
            direct_messages=direct_messages,
            context_messages=context_messages,
            room_map=room_map,
        )
        return context_messages

    def _apply_context_reasons(
        self,
        *,
        direct_messages: list[dict[str, Any]],
        context_messages: dict[str, dict[str, Any]],
        room_map: dict[str, dict[str, Any]],
    ) -> None:
        direct_ids = {str(message["_id"]) for message in direct_messages}
        replied_to_ids = {
            str(message["tmid"])
            for message in direct_messages
            if message.get("tmid")
        }
        for message_id, message in context_messages.items():
            tmid = str(message.get("tmid")) if message.get("tmid") else None
            if tmid in direct_ids:
                message["_context_reason"] = "reply-to-direct-match"
            elif message_id in replied_to_ids:
                message["_context_reason"] = "original-of-direct-reply"
            else:
                message["_context_reason"] = "thread-context"

    def _message_starts_thread(self, message: dict[str, Any]) -> bool:
        return bool(message.get("tcount") or message.get("tlm"))

    def _normalize_message(
        self,
        message: dict[str, Any],
        *,
        room_map: dict[str, dict[str, Any]],
    ) -> dict[str, object]:
        room_id = str(message.get("rid", ""))
        room = room_map.get(room_id, {})
        user = message.get("u") or {}
        attachments = [
            {
                "title": attachment.get("title"),
                "type": attachment.get("type"),
                "description": attachment.get("description"),
                "title_link": attachment.get("title_link"),
                "image_url": attachment.get("image_url"),
                "audio_url": attachment.get("audio_url"),
                "video_url": attachment.get("video_url"),
                "mime_type": attachment.get("mimeType"),
            }
            for attachment in message.get("attachments", [])
        ]
        mentions = [
            {
                "user_id": mention.get("_id"),
                "username": mention.get("username"),
                "name": mention.get("name"),
            }
            for mention in message.get("mentions", [])
        ]

        normalized = {
            "message_id": str(message.get("_id")),
            "room": {
                "room_id": room_id,
                "name": room.get("fname") or room.get("name"),
                "room_type": room.get("t"),
            },
            "user": {
                "user_id": user.get("_id"),
                "username": user.get("username"),
                "name": user.get("name"),
            },
            "created_at": serialize_datetime(self._safe_datetime(message.get("ts"))),
            "updated_at": serialize_datetime(self._safe_datetime(message.get("_updatedAt"))),
            "text": message.get("msg", ""),
            "message_type": message.get("t"),
            "thread_id": str(message.get("tmid")) if message.get("tmid") else None,
            "parent_message_id": str(message.get("tmid")) if message.get("tmid") else None,
            "replies_count": message.get("tcount", 0),
            "is_thread_message": bool(message.get("tmid")),
            "mentions": mentions,
            "reactions": message.get("reactions") or {},
            "attachments": attachments,
            "context_reason": message.get("_context_reason", "direct-match"),
            "raw": self._sanitize_raw(message),
        }
        if self.options.mode == "content-only":
            return {
                "message_id": normalized["message_id"],
                "created_at": normalized["created_at"],
                "text": normalized["text"],
                "username": normalized["user"]["username"],
                "room_name": normalized["room"]["name"],
                "thread_id": normalized["thread_id"],
                "context_reason": normalized["context_reason"],
            }
        return normalized

    def _sanitize_raw(self, message: dict[str, Any]) -> dict[str, object]:
        safe: dict[str, object] = {}
        for key, value in message.items():
            if key == "_context_reason":
                continue
            safe[key] = self._serialize_raw_value(value)
        return safe

    def _serialize_raw_value(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return serialize_datetime(value)
        if isinstance(value, list):
            return [self._serialize_raw_value(item) for item in value]
        if isinstance(value, dict):
            return {key: self._serialize_raw_value(item) for key, item in value.items()}
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        return str(value)

    def _safe_datetime(self, value: Any) -> datetime | None:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _build_summary(
        self,
        messages: list[dict[str, object]],
        *,
        direct_count: int,
    ) -> dict[str, object]:
        by_reason: dict[str, int] = defaultdict(int)
        by_room: dict[str, int] = defaultdict(int)
        for message in messages:
            reason = str(message.get("context_reason", "direct-match"))
            by_reason[reason] += 1
            room_name = self._extract_room_name(message)
            by_room[room_name] += 1
        return {
            "database": self.options.database_name,
            "message_count": len(messages),
            "direct_match_count": direct_count,
            "smart_context": self.options.smart_context,
            "format": self.options.format,
            "mode": self.options.mode,
            "filters": {
                "room_ids": sorted(self.options.filters.room_ids),
                "room_names": sorted(self.options.filters.room_names),
                "excluded_room_ids": sorted(self.options.filters.excluded_room_ids),
                "excluded_room_names": sorted(self.options.filters.excluded_room_names),
                "user_ids": sorted(self.options.filters.user_ids),
                "usernames": sorted(self.options.filters.usernames),
                "date_from": serialize_datetime(self.options.filters.date_from),
                "date_to": serialize_datetime(self.options.filters.date_to),
                "dates": [
                    serialize_datetime(value)
                    for value in sorted(self.options.filters.dates)
                ],
            },
            "context_reason_counts": dict(by_reason),
            "room_counts": dict(by_room),
        }

    def _extract_room_name(self, message: dict[str, object]) -> str:
        room = message.get("room")
        if isinstance(room, dict):
            return str(room.get("name") or room.get("room_id") or "unknown")
        return str(message.get("room_name") or "unknown")

    def _sort_key(self, message: dict[str, Any]) -> tuple[datetime, str]:
        created_at = self._safe_datetime(message.get("ts")) or datetime.min.replace(tzinfo=UTC)
        return created_at, str(message.get("_id"))

    def _build_context_room_query(
        self,
        room_map: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        excluded_room_ids = set(self.options.filters.excluded_room_ids)
        if self.options.filters.excluded_room_names:
            excluded_room_ids.update(
                self._resolve_room_ids(room_map, self.options.filters.excluded_room_names)
            )
        return self._build_room_query(
            included_room_ids=set(),
            excluded_room_ids=excluded_room_ids,
        )

    def _build_room_query(
        self,
        *,
        included_room_ids: set[str],
        excluded_room_ids: set[str],
    ) -> dict[str, Any] | None:
        if included_room_ids and excluded_room_ids:
            effective_ids = included_room_ids - excluded_room_ids
            return {"$in": sorted(effective_ids)}
        if included_room_ids:
            return {"$in": sorted(included_room_ids)}
        if excluded_room_ids:
            return {"$nin": sorted(excluded_room_ids)}
        return None
