from __future__ import annotations

import argparse
import sys
import unittest
from datetime import UTC
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rocketchat_exporter.cli import parse_filters


class ParseFiltersTests(unittest.TestCase):
    def test_parse_filters_reads_cli_values(self) -> None:
        args = argparse.Namespace(
            date=["2026-04-01,2026-04-03"],
            date_from="2026-04-01",
            date_to="2026-04-30",
            room_id=["room-a"],
            room_name=["general,random"],
            user_id=["user-1"],
            username=["alice,bob"],
            no_replies=False,
            no_originals=True,
        )

        filters = parse_filters(args, {})

        self.assertEqual(filters.room_ids, {"room-a"})
        self.assertEqual(filters.room_names, {"general", "random"})
        self.assertEqual(filters.user_ids, {"user-1"})
        self.assertEqual(filters.usernames, {"alice", "bob"})
        self.assertEqual({item.day for item in filters.dates}, {1, 3})
        self.assertEqual(filters.date_from.tzinfo, UTC)
        self.assertEqual(filters.date_to.hour, 23)
        self.assertTrue(filters.include_replies)
        self.assertFalse(filters.include_originals)

    def test_parse_filters_falls_back_to_config(self) -> None:
        args = argparse.Namespace(
            date=None,
            date_from=None,
            date_to=None,
            room_id=None,
            room_name=None,
            user_id=None,
            username=None,
            no_replies=False,
            no_originals=False,
        )
        config = {
            "room_names": ["support"],
            "usernames": ["alice"],
            "dates": ["2026-04-05"],
            "no_replies": True,
        }

        filters = parse_filters(args, config)

        self.assertEqual(filters.room_names, {"support"})
        self.assertEqual(filters.usernames, {"alice"})
        self.assertEqual(len(filters.dates), 1)
        self.assertFalse(filters.include_replies)


if __name__ == "__main__":
    unittest.main()
