import unittest

from promo_core import (
    TimelineEvent,
    episode_label,
    parse_model_result,
    parse_timeline,
    timestamp_to_seconds,
)


class PromoCoreTests(unittest.TestCase):
    def test_parse_timestamped_events_and_label(self):
        script = """EPISODE NUMBER: Episode 7
**LADY JULIANA (Angry):**
Start: (00:01.00) | End: (00:22.00)
"You betrayed me."
**ACTION:**
Start: (00:22.00) | End: (00:35.00)
She turns and leaves.
"""
        events = parse_timeline(script)
        self.assertEqual(episode_label("episode-007.txt", script), "Episode 7")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].label, "LADY JULIANA (Angry):")
        self.assertEqual(events[1].text, "She turns and leaves.")

    def test_validates_duration_and_source_boundaries(self):
        events = [
            TimelineEvent("00:00.00", "00:22.00", "DIALOGUE", "Opening."),
            TimelineEvent("00:22.00", "00:35.00", "ACTION", "She leaves."),
        ]
        raw = """{"promos":[
          {"start_time":"00:00.00","end_time":"00:35.00","hook":"A betrayal",
           "cliffhanger":"She leaves","why_it_works":"Clear stakes","score":8},
          {"start_time":"00:01.00","end_time":"00:35.00","hook":"Hook",
           "cliffhanger":"End","why_it_works":"Reason","score":7}
        ]}"""
        accepted, rejected = parse_model_result(raw, events)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["duration_seconds"], 35.0)
        self.assertEqual(len(rejected), 1)
        self.assertAlmostEqual(timestamp_to_seconds("00:35.00"), 35)


if __name__ == "__main__":
    unittest.main()
