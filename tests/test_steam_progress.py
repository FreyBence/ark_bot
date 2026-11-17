import unittest
from steam_progress import SteamProgress


class ProgressTests(unittest.TestCase):
    def test_chunked_carriage_return_progress_and_stage_reset(self):
        p = SteamProgress()
        p.feed("Update state (0x61) downloading, progress: 2")
        p.feed("5.50 (255 / 1000)\r")
        self.assertEqual(p.stage, "Downloading files")
        self.assertEqual(p.percent, 25.5)
        p.feed("Update state (0x5) verifying, progress: 8.0\n")
        self.assertEqual(p.stage, "Validating files")
        self.assertEqual(p.percent, 8.0)
        p.feed("Success! App '2430930' fully installed.\n")
        self.assertIsNone(p.percent)

    def test_unknown_output_does_not_invent_a_percentage(self):
        p = SteamProgress()
        p.feed("Steam Console Client\nLogging in anonymously\n")
        self.assertEqual(p.stage, "Connecting to Steam")
        self.assertIsNone(p.percent)
        self.assertIn("Progress percentage is not available", p.render("Initializing"))
        p.feed("already up to ")
        p.feed("date\n")
        self.assertTrue(p.already_current)


if __name__ == "__main__":
    unittest.main()
