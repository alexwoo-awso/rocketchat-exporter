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

Once published to PyPI, install will be:

```bash
pip install rocketchat-exporter
```

## Future npm Publish

The repository now includes `package.json` and an npm bin wrapper in `bin/rocketchat-exporter.js`.

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

## Docker Usage

You can run the exporter as a one-shot Docker container attached to the same Docker network as Rocket.Chat and MongoDB.

Pull the prebuilt image from GHCR:

```bash
docker pull ghcr.io/alexwoo-awso/rocketchat-exporter:latest
```

Run it on the existing Rocket.Chat network:

```bash
docker run --rm \
  --network YOUR_ROCKETCHAT_NETWORK \
  -v "$PWD/exports:/work/exports" \
  ghcr.io/alexwoo-awso/rocketchat-exporter:latest \
  --mongo-uri "mongodb://mongodb:27017/rocketchat?authSource=admin" \
  --database rocketchat \
  --username alice \
  --smart-context \
  --format html \
  --output /work/exports/alice.html
```

If your Mongo service name inside Docker Compose is not `mongodb`, use the actual compose service name instead.

You can also run it with a mounted config file:

```bash
docker run --rm \
  --network YOUR_ROCKETCHAT_NETWORK \
  -v "$PWD/config.json:/work/config.json:ro" \
  -v "$PWD/exports:/work/exports" \
  ghcr.io/alexwoo-awso/rocketchat-exporter:latest \
  --config /work/config.json
```

An example compose file is included in `docker-compose.exporter.example.yml`. Set the external network name to the existing Rocket.Chat Docker network before using it.

Notes:

- The container is designed for one-shot exports, not a long-running service.
- GitHub releases publish the image to `ghcr.io/alexwoo-awso/rocketchat-exporter`.
- Use Docker-network hostnames from your Rocket.Chat stack for `--mongo-uri`.
- For `json-with-attachments`, also set `--attachment-base-url` to your Rocket.Chat base URL.
- Write outputs to a mounted host directory such as `/work/exports`.

## Filters

- `--room-id`, `--room-name`: repeatable and comma-separated
- `--exclude-room-id`, `--exclude-room-name`: optional room exclusions, repeatable and comma-separated
- `--user-id`, `--username`: repeatable and comma-separated
- `--date-from`, `--date-to`: inclusive UTC range
- `--date`: specific UTC dates to include; can be repeated

If both explicit dates and a range are provided, both constraints apply.
Excluded rooms are removed from both direct matches and smart-context expansion.

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

## PyPI Release Setup

The repo is configured for PyPI publishing through GitHub Actions with Trusted Publishing.

Before the first release:

1. Create the PyPI project or publish the first release from GitHub Actions.
2. In PyPI, add a Trusted Publisher for this repository:
   - owner: `alexwoo-awso`
   - repository: `rocketchat-exporter`
   - workflow: `pypi-publish.yml`
   - environment: `pypi`
3. In GitHub, keep the `pypi` environment enabled for the publish workflow.

Release flow:

1. Bump `version` in `pyproject.toml`.
2. Create a GitHub release.
3. The `Publish To PyPI` workflow builds, validates, and uploads the package.
