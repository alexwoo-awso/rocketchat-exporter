from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rocketchat_exporter.exporters import export_messages
from rocketchat_exporter.models import ExportOptions, Filters


class ExporterTests(unittest.TestCase):
    def test_html_export_writes_message_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "export.html"
            options = ExportOptions(
                mongo_uri="mongodb://example",
                database_name="rocketchat",
                format="html",
                mode="content-only",
                output_path=output,
                filters=Filters(),
            )

            export_messages(
                messages=[
                    {
                        "message_id": "m1",
                        "created_at": "2026-04-01T12:00:00Z",
                        "text": "Hello world",
                        "username": "alice",
                        "room_name": "General",
                        "context_reason": "direct-match",
                    }
                ],
                summary={"message_count": 1},
                options=options,
            )

            html_output = output.read_text(encoding="utf-8")
            self.assertIn("Hello world", html_output)
            self.assertIn("direct-match", html_output)

    def test_json_export_writes_summary_and_messages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "export.json"
            options = ExportOptions(
                mongo_uri="mongodb://example",
                database_name="rocketchat",
                format="json",
                mode="full",
                output_path=output,
                filters=Filters(),
            )

            export_messages(
                messages=[{"message_id": "m1", "text": "Hello"}],
                summary={"message_count": 1},
                options=options,
            )

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["message_count"], 1)
            self.assertEqual(payload["messages"][0]["message_id"], "m1")


if __name__ == "__main__":
    unittest.main()
