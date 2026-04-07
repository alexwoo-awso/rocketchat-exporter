from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from rocketchat_exporter.exporters import export_messages
from rocketchat_exporter.models import ExportOptions, Filters
from rocketchat_exporter.service import RocketChatExportService
from rocketchat_exporter.utils import parse_csv, parse_iso_datetime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rocketchat-exporter",
        description="Export Rocket.Chat messages from MongoDB with granular filters.",
    )
    parser.add_argument(
        "--config",
        help="Optional JSON config file. CLI arguments override config values.",
    )
    parser.add_argument("--mongo-uri", help="MongoDB connection URI.")
    parser.add_argument(
        "--database",
        help="Rocket.Chat MongoDB database name.",
    )
    parser.add_argument(
        "--room-id",
        action="append",
        help="Room ID filter. Repeat or pass comma-separated values.",
    )
    parser.add_argument(
        "--room-name",
        action="append",
        help="Room name filter. Repeat or pass comma-separated values.",
    )
    parser.add_argument(
        "--exclude-room-id",
        action="append",
        help="Room ID exclusion filter. Repeat or pass comma-separated values.",
    )
    parser.add_argument(
        "--exclude-room-name",
        action="append",
        help="Room name exclusion filter. Repeat or pass comma-separated values.",
    )
    parser.add_argument(
        "--user-id",
        action="append",
        help="User ID filter. Repeat or pass comma-separated values.",
    )
    parser.add_argument(
        "--username",
        action="append",
        help="Username filter. Repeat or pass comma-separated values.",
    )
    parser.add_argument(
        "--date-from",
        help="Inclusive UTC lower bound. ISO date or datetime.",
    )
    parser.add_argument(
        "--date-to",
        help="Inclusive UTC upper bound. ISO date or datetime.",
    )
    parser.add_argument(
        "--date",
        action="append",
        help="Specific UTC day(s) to include. Repeat or pass comma-separated values.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "json-with-attachments", "html"],
        help="Output format.",
    )
    parser.add_argument(
        "--mode",
        choices=["full", "content-only"],
        help="Export all metadata or content-focused output only.",
    )
    parser.add_argument(
        "--output",
        help="Output file path.",
    )
    parser.add_argument(
        "--attachments-dir",
        help="Directory for downloaded attachments when using json-with-attachments.",
    )
    parser.add_argument(
        "--attachment-base-url",
        help="Optional absolute base URL used to download attachment paths.",
    )
    parser.add_argument(
        "--smart-context",
        action="store_true",
        help="Expand direct user matches with replies and replied-to originals.",
    )
    parser.add_argument(
        "--no-replies",
        action="store_true",
        help="Disable collecting replies to matched messages in smart mode.",
    )
    parser.add_argument(
        "--no-originals",
        action="store_true",
        help="Disable collecting original messages a matched user replied to in smart mode.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Disable pretty-printed JSON output.",
    )
    return parser


def parse_filters(args: argparse.Namespace, config: dict[str, Any]) -> Filters:
    date_from = _read_scalar_value(args.date_from, config, "date_from", "date-from")
    date_to = _read_scalar_value(args.date_to, config, "date_to", "date-to")
    selected_dates = {
        parse_iso_datetime(item)
        for item in _read_multi_value(args.date, config, "dates", "date")
    }
    return Filters(
        room_ids=set(_read_multi_value(args.room_id, config, "room_ids", "room_id", "room-id")),
        room_names=set(
            _read_multi_value(args.room_name, config, "room_names", "room_name", "room-name")
        ),
        excluded_room_ids=set(
            _read_multi_value(
                args.exclude_room_id,
                config,
                "excluded_room_ids",
                "exclude_room_ids",
                "exclude_room_id",
                "exclude-room-ids",
                "exclude-room-id",
            )
        ),
        excluded_room_names=set(
            _read_multi_value(
                args.exclude_room_name,
                config,
                "excluded_room_names",
                "exclude_room_names",
                "exclude_room_name",
                "exclude-room-names",
                "exclude-room-name",
            )
        ),
        user_ids=set(_read_multi_value(args.user_id, config, "user_ids", "user_id", "user-id")),
        usernames=set(
            _read_multi_value(args.username, config, "usernames", "username")
        ),
        dates=selected_dates,
        date_from=parse_iso_datetime(str(date_from)) if date_from else None,
        date_to=parse_iso_datetime(str(date_to), end_of_day=True) if date_to else None,
        include_replies=not _read_bool_flag(
            args.no_replies,
            config,
            "no_replies",
            "no-replies",
        ),
        include_originals=not _read_bool_flag(
            args.no_originals,
            config,
            "no_originals",
            "no-originals",
        ),
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = load_config(args.config)
    mongo_uri = _read_required_value(args.mongo_uri, config, "mongo_uri", "mongo-uri")
    database = _read_required_value(args.database, config, "database")
    output = _read_required_value(args.output, config, "output")
    output_format = _read_scalar_value(args.format, config, "format") or "json"
    mode = _read_scalar_value(args.mode, config, "mode") or "full"
    attachments_dir = _read_scalar_value(
        args.attachments_dir,
        config,
        "attachments_dir",
        "attachments-dir",
    )
    attachment_base_url = _read_scalar_value(
        args.attachment_base_url,
        config,
        "attachment_base_url",
        "attachment-base-url",
    )
    smart_context = _read_bool_flag(
        args.smart_context,
        config,
        "smart_context",
        "smart-context",
    )
    compact = _read_bool_flag(args.compact, config, "compact")

    options = ExportOptions(
        mongo_uri=str(mongo_uri),
        database_name=str(database),
        format=str(output_format),
        mode=str(mode),
        output_path=Path(str(output)),
        attachments_dir=Path(str(attachments_dir))
        if attachments_dir
        else None,
        attachment_base_url=str(attachment_base_url) if attachment_base_url else None,
        smart_context=smart_context,
        filters=parse_filters(args, config),
        pretty=not compact,
    )

    service = RocketChatExportService(options)
    messages, summary = service.collect_messages()
    export_messages(messages=messages, summary=summary, options=options)
    print(json.dumps(summary, indent=2 if options.pretty else None))
    return 0


def load_config(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    config_path = Path(path)
    return json.loads(config_path.read_text(encoding="utf-8"))


def _read_required_value(
    cli_value: object | None,
    config: dict[str, Any],
    *keys: str,
) -> object:
    value = _read_scalar_value(cli_value, config, *keys)
    if value is None or value == "":
        joined = ", ".join(keys)
        raise SystemExit(f"Missing required option. Provide it via CLI or config: {joined}")
    return value


def _read_scalar_value(
    cli_value: object | None,
    config: dict[str, Any],
    *keys: str,
) -> object | None:
    if cli_value not in (None, ""):
        return cli_value
    for key in keys:
        if key in config and config[key] not in (None, ""):
            return config[key]
    return None


def _read_multi_value(
    cli_value: list[str] | None,
    config: dict[str, Any],
    *keys: str,
) -> list[str]:
    if cli_value:
        return sorted(parse_csv(cli_value))
    for key in keys:
        if key not in config or config[key] in (None, ""):
            continue
        value = config[key]
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        return sorted(parse_csv([str(value)]))
    return []


def _read_bool_flag(
    cli_value: bool,
    config: dict[str, Any],
    *keys: str,
) -> bool:
    if cli_value:
        return True
    for key in keys:
        if key in config:
            return bool(config[key])
    return False
