# Rocket.Chat Exporter

CLI app for exporting Rocket.Chat message data directly from MongoDB with:

- room filters by ID and name
- user filters by ID and username
- inclusive date range filtering
- multiple explicitly selected dates
- metadata or content-only export modes
- smart context expansion for replies and replied-to originals
- multiple export formats including JSON and HTML

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

## Future npm Publish

The repository now includes [package.json](C:/Users/olek/Documents/GitHub/rocketchat-exporter/package.json) and an npm bin wrapper at [rocketchat-exporter.js](C:/Users/olek/Documents/GitHub/rocketchat-exporter/bin/rocketchat-exporter.js).

That gives you a clean future npm publishing path with the same `rocketchat-exporter` command name, but this remains a Python application. The npm package will still require Python 3.11+ and Python dependencies on the target server unless you later switch to shipping a standalone binary build.

## Usage

```bash
rocketchat-exporter ^
  --mongo-uri "mongodb://localhost:27017/?directConnection=true" ^
  --database rocketchat ^
  --room-name general ^
  --username alice,bob ^
  --date-from 2026-04-01 ^
  --date-to 2026-04-30 ^
  --smart-context ^
  --format html ^
  --output exports\april.html
```

Or use a config file:

```bash
rocketchat-exporter --config config.example.json
```

## Filters

- `--room-id`, `--room-name`: repeatable and comma-separated
- `--user-id`, `--username`: repeatable and comma-separated
- `--date-from`, `--date-to`: inclusive UTC range
- `--date`: specific UTC dates to include; can be repeated

If both explicit dates and a range are provided, both constraints apply.

## Smart Context

`--smart-context` starts from direct matches and then adds:

- replies to matched thread-starting messages
- original messages that matched users replied to

This preserves focused conversational context without exporting the full room history.

Use `--no-replies` or `--no-originals` to disable either side of the expansion.

## Formats

- `json`: summary + normalized messages
- `json-with-attachments`: same JSON, plus attachment download attempts and local file paths
- `html`: readable single-file export

For relative attachment URLs, set `--attachment-base-url`.

## Modes

- `full`: metadata, normalized fields, and raw message payload
- `content-only`: compact content-focused export
