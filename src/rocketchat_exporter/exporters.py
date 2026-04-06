from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

from rocketchat_exporter.models import ExportOptions
from rocketchat_exporter.utils import ensure_directory


def export_messages(
    *,
    messages: list[dict[str, object]],
    summary: dict[str, object],
    options: ExportOptions,
) -> None:
    ensure_directory(options.output_path.parent)
    if options.format == "json":
        _write_json(options.output_path, {"summary": summary, "messages": messages}, options)
        return
    if options.format == "json-with-attachments":
        payload = _download_attachments(messages=messages, options=options)
        _write_json(options.output_path, {"summary": summary, "messages": payload}, options)
        return
    if options.format == "html":
        options.output_path.write_text(_build_html(messages, summary), encoding="utf-8")
        return
    raise ValueError(f"Unsupported format: {options.format}")


def _write_json(path: Path, payload: dict[str, object], options: ExportOptions) -> None:
    path.write_text(
        json.dumps(payload, indent=2 if options.pretty else None, ensure_ascii=False),
        encoding="utf-8",
    )


def _download_attachments(
    *,
    messages: list[dict[str, object]],
    options: ExportOptions,
) -> list[dict[str, object]]:
    attachments_dir = options.attachments_dir or options.output_path.with_suffix("")
    ensure_directory(attachments_dir)
    enriched_messages = []

    for message in messages:
        attachments = message.get("attachments")
        if not isinstance(attachments, list):
            enriched_messages.append(message)
            continue

        enriched_attachments = []
        for index, attachment in enumerate(attachments, start=1):
            if not isinstance(attachment, dict):
                enriched_attachments.append(attachment)
                continue
            enriched_attachments.append(
                _download_attachment(
                    attachment=attachment,
                    attachments_dir=attachments_dir,
                    base_url=options.attachment_base_url,
                    message_id=str(message.get("message_id", "message")),
                    index=index,
                )
            )
        enriched_message = dict(message)
        enriched_message["attachments"] = enriched_attachments
        enriched_messages.append(enriched_message)
    return enriched_messages


def _download_attachment(
    *,
    attachment: dict[str, object],
    attachments_dir: Path,
    base_url: str | None,
    message_id: str,
    index: int,
) -> dict[str, object]:
    candidate_url = _extract_attachment_url(attachment)
    if not candidate_url:
        return attachment

    absolute_url = _resolve_attachment_url(candidate_url, base_url)
    if not absolute_url:
        result = dict(attachment)
        result["download_error"] = "attachment-base-url is required for relative URLs"
        return result

    extension = Path(urlparse(absolute_url).path).suffix or ".bin"
    target_name = f"{message_id}-{index}{extension}"
    target_path = attachments_dir / target_name

    result = dict(attachment)
    try:
        with urlopen(absolute_url) as response:
            target_path.write_bytes(response.read())
        result["downloaded_to"] = str(target_path)
        result["source_url"] = absolute_url
    except Exception as exc:
        result["download_error"] = str(exc)
        result["source_url"] = absolute_url
    return result


def _extract_attachment_url(attachment: dict[str, object]) -> str | None:
    for key in ("title_link", "image_url", "audio_url", "video_url"):
        value = attachment.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _resolve_attachment_url(url: str, base_url: str | None) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return url
    if not base_url:
        return None
    return urljoin(base_url.rstrip("/") + "/", url.lstrip("/"))


def _build_html(messages: list[dict[str, object]], summary: dict[str, object]) -> str:
    stats = "".join(
        (
            f"<li><strong>{html.escape(str(key))}</strong>: "
            f"{html.escape(json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value))}</li>"
        )
        for key, value in summary.items()
    )
    rows = "".join(_render_html_message(message) for message in messages)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Rocket.Chat Export</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f4ee;
      --panel: #fffdf8;
      --line: #d9cfbe;
      --ink: #201814;
      --muted: #6e6258;
      --accent: #8f3d27;
    }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      background: radial-gradient(circle at top, #fff8ec 0%, var(--bg) 55%);
      color: var(--ink);
    }}
    main {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 32px 18px 48px;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 20px;
      margin-bottom: 18px;
      box-shadow: 0 12px 30px rgba(32, 24, 20, 0.06);
    }}
    h1, h2 {{
      margin-top: 0;
    }}
    ul {{
      padding-left: 20px;
    }}
    article {{
      padding: 14px 0;
      border-top: 1px solid var(--line);
    }}
    article:first-child {{
      border-top: 0;
      padding-top: 0;
    }}
    .meta {{
      color: var(--muted);
      font-size: 0.95rem;
      margin-bottom: 6px;
    }}
    .reason {{
      color: var(--accent);
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      font-size: 0.75rem;
    }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      margin: 10px 0 0;
      font-family: "Courier New", monospace;
      background: #fcf7ee;
      border-radius: 12px;
      padding: 12px;
      border: 1px solid #eadfce;
    }}
  </style>
</head>
<body>
  <main>
    <section>
      <h1>Rocket.Chat Export</h1>
      <ul>{stats}</ul>
    </section>
    <section>
      <h2>Messages</h2>
      {rows}
    </section>
  </main>
</body>
</html>"""


def _render_html_message(message: dict[str, object]) -> str:
    username = _dig(message, "user", "username") or message.get("username") or "unknown"
    room_name = _dig(message, "room", "name") or message.get("room_name") or "unknown"
    created_at = message.get("created_at") or ""
    reason = message.get("context_reason") or "direct-match"
    text = message.get("text") or ""
    return (
        "<article>"
        f'<div class="reason">{html.escape(str(reason))}</div>'
        f'<div class="meta">{html.escape(str(created_at))} | '
        f'{html.escape(str(room_name))} | {html.escape(str(username))}</div>'
        f"<pre>{html.escape(str(text))}</pre>"
        "</article>"
    )


def _dig(message: dict[str, object], parent_key: str, key: str) -> object | None:
    parent = message.get(parent_key)
    if not isinstance(parent, dict):
        return None
    return parent.get(key)
