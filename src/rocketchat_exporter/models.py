from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal


ExportFormat = Literal["json", "json-with-attachments", "html"]
ExportMode = Literal["full", "content-only"]


@dataclass(slots=True)
class UserRef:
    user_id: str | None
    username: str | None
    name: str | None


@dataclass(slots=True)
class RoomRef:
    room_id: str
    name: str | None
    room_type: str | None


@dataclass(slots=True)
class AttachmentFile:
    title: str | None
    type: str | None
    description: str | None
    title_link: str | None
    image_url: str | None
    audio_url: str | None
    video_url: str | None
    mime_type: str | None


@dataclass(slots=True)
class MessageRecord:
    message_id: str
    room: RoomRef
    user: UserRef
    created_at: datetime
    updated_at: datetime | None
    text: str
    message_type: str | None
    thread_id: str | None
    parent_message_id: str | None
    replies_count: int
    is_thread_message: bool
    mentions: list[dict[str, str | None]] = field(default_factory=list)
    reactions: dict[str, object] = field(default_factory=dict)
    attachments: list[AttachmentFile] = field(default_factory=list)
    raw: dict[str, object] = field(default_factory=dict)
    context_reason: str = "direct-match"


@dataclass(slots=True)
class Filters:
    room_ids: set[str] = field(default_factory=set)
    room_names: set[str] = field(default_factory=set)
    excluded_room_ids: set[str] = field(default_factory=set)
    excluded_room_names: set[str] = field(default_factory=set)
    user_ids: set[str] = field(default_factory=set)
    usernames: set[str] = field(default_factory=set)
    dates: set[datetime] = field(default_factory=set)
    date_from: datetime | None = None
    date_to: datetime | None = None
    include_replies: bool = True
    include_originals: bool = True


@dataclass(slots=True)
class ExportOptions:
    mongo_uri: str
    database_name: str
    format: ExportFormat
    mode: ExportMode
    output_path: Path
    filters: Filters
    attachments_dir: Path | None = None
    attachment_base_url: str | None = None
    smart_context: bool = False
    pretty: bool = True
