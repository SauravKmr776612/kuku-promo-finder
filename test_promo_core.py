import unittest

from promo_core import (
    TimelineEvent,
    build_batch_prompt,
    call_with_retries,
    episode_label,
    parse_batch_model_result,
    parse_model_result,
    parse_timeline,
    timestamp_to_seconds,
)


class PromoCoreTests(unittest.TestCase):
    def test_retries_temporary_server_error(self):
        class FakeError(Exception):
            code = 503

        calls = []
        delays = []

        def request():
            calls.append(None)
            if len(calls) == 1:
                raise FakeError("temporary overload")
            return "success"

        result = call_with_retries(request, sleep=delays.append)
        self.assertEqual(result, "success")
        self.assertEqual(delays, [5])

    def test_uses_retry_delay_for_rate_limit_error(self):
        class FakeError(Exception):
            code = 429

        calls = []
        delays = []

        def request():
            calls.append(None)
            if len(calls) == 1:
                raise FakeError("Please retry in 44.5s.")
            return "success"

        result = call_with_retries(request, sleep=delays.append)
        self.assertEqual(result, "success")
        self.assertEqual(delays, [45.5])

    def test_does_not_retry_other_errors(self):
        class FakeError(Exception):
            code = 400

        delays = []
        with self.assertRaises(FakeError):
            call_with_retries(lambda: (_ for _ in ()).throw(FakeError()), sleep=delays.append)
        self.assertEqual(delays, [])

    def test_does_not_retry_daily_quota_exhaustion(self):
        class FakeError(Exception):
            code = 429

            def __str__(self):
                return "Generate content requests per day limit exceeded."

        calls = []
        delays = []

        def request():
            calls.append(None)
            raise FakeError()

        with self.assertRaises(FakeError):
            call_with_retries(request, sleep=delays.append)
        self.assertEqual(len(calls), 1)
        self.assertEqual(delays, [])

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

    def test_batch_prompt_and_results_keep_episode_boundaries(self):
        events = [
            TimelineEvent("00:00.00", "00:22.00", "DIALOGUE", "Opening."),
            TimelineEvent("00:22.00", "00:35.00", "ACTION", "She leaves."),
        ]
        episodes = {"Episode 1": events, "Episode 2": events}
        prompt = build_batch_prompt(episodes)
        self.assertIn('"Episode 1"', prompt)
        self.assertIn('"Episode 2"', prompt)

        raw = """{"promos":[
          {"episode":"Episode 2","start_time":"00:00.00","end_time":"00:35.00",
           "hook":"A betrayal","cliffhanger":"She leaves",
           "why_it_works":"Clear stakes","score":8},
          {"episode":"Episode 9","start_time":"00:00.00","end_time":"00:35.00",
           "hook":"Hook","cliffhanger":"End","why_it_works":"Reason","score":7}
        ]}"""
        accepted, rejected = parse_batch_model_result(raw, episodes)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]["episode"], "Episode 2")
        self.assertEqual(len(rejected), 1)


if __name__ == "__main__":
    unittest.main()
