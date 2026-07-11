from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import unittest

from organizer.web.formatting import (
    folder_name,
    format_bytes,
    format_local_time,
    format_local_timestamp,
    readable_folder,
)


class ConsumerFormattingTests(unittest.TestCase):
    def test_bytes_use_readable_binary_units(self) -> None:
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(160), "160 B")
        self.assertEqual(format_bytes(5_325), "5.2 KB")
        self.assertEqual(format_bytes(15_519_539), "14.8 MB")
        self.assertEqual(format_bytes(1_503_238_553), "1.4 GB")
        self.assertEqual(format_bytes(None), "Not available")
        self.assertEqual(format_bytes(-1), "Not available")

    def test_times_use_today_yesterday_and_explicit_date(self) -> None:
        local_zone = datetime.now().astimezone().tzinfo
        assert local_zone is not None
        now = datetime(2026, 7, 11, 15, 0, tzinfo=local_zone)
        self.assertEqual(
            format_local_time(now.replace(hour=3, minute=12), now=now),
            "Today, 3:12 AM",
        )
        self.assertEqual(
            format_local_time(now - timedelta(days=1, hours=5, minutes=20), now=now),
            "Yesterday, 9:40 AM",
        )
        self.assertEqual(
            format_local_time(
                datetime(2026, 7, 10, 16, 30, tzinfo=local_zone),
                now=datetime(2026, 7, 12, tzinfo=local_zone),
            ),
            "10 Jul 2026, 4:30 PM",
        )
        self.assertEqual(format_local_time(None), "Not available")
        self.assertEqual(format_local_timestamp(None), "Not available")

    def test_folder_names_are_consumer_readable(self) -> None:
        root = Path("/Users/person/Downloads")
        self.assertEqual(folder_name(root), "Downloads")
        self.assertEqual(
            readable_folder(root / "EvoSim" / "Notes", root, include_root=False),
            "EvoSim → Notes",
        )
        self.assertEqual(
            readable_folder(root, root, include_root=True),
            "Downloads",
        )


if __name__ == "__main__":
    unittest.main()
