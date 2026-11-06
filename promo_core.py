import json
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, TypeVar


T = TypeVar("T")


TIMESTAMP_PATTERN = re.compile(
    r"(?m)^\s*Start:\s*\((\d{2}:\d{2}\.\d{2})\)\s*\|\s*"
    r"End:\s*\((\d{2}:\d{2}\.\d{2})\)\s*$"
)


@dataclass(frozen=True)
class TimelineEvent:
    start: str
    end: str
    label: str
    text: str


def timestamp_to_seconds(timestamp: str) -> float:
    minutes, seconds = timestamp.split(":")
    return int(minutes) * 60 + float(seconds)


def call_with_retries(
    request: Callable[[], T],
    sleep: Callable[[float], None] = time.sleep,
    max_attempts: int = 3,
) -> T:
    for attempt in range(max_attempts):
        try:
            return request()
        except Exception as exc:
            status_code = getattr(exc, "code", None)
            error_message = str(exc).lower()
            if status_code == 429 and "per day limit exceeded" in error_message:
                raise
            if status_code not in (429, 503) or attempt == max_attempts - 1:
                raise

            if status_code == 429:
                match = re.search(r"retry in ([\d.]+)s", str(exc), re.IGNORECASE)
                delay = float(match.group(1)) + 1 if match else 60
            else:
                delay = 5 * (2**attempt)
            sleep(delay)

    raise RuntimeError("Request retry loop ended unexpectedly.")


def parse_timeline(script: str) -> list[TimelineEvent]:
    matches = list(TIMESTAMP_PATTERN.finditer(script))
    events: list[TimelineEvent] = []

    for index, match in enumerate(matches):
        previous_end = matches[index - 1].end() if index else 0
        heading_pattern = re.compile(r"(?m)^\s*\*\*(.+?)\*\*:?\s*$")
        headings = list(heading_pattern.finditer(script, previous_end, match.start()))
        label = headings[-1].group(1).strip() if headings else "SCRIPT"

        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(script)
        next_heading = heading_pattern.search(script, match.end(), body_end)
        if next_heading:
            body_end = next_heading.start()
        body = script[match.end():body_end].strip()

        text = re.sub(r"\s+", " ", body).strip()
        start_seconds = timestamp_to_seconds(match.group(1))
        end_seconds = timestamp_to_seconds(match.group(2))
        if text and end_seconds > start_seconds:
            events.append(
                TimelineEvent(
                    start=match.group(1),
                    end=match.group(2),
                    label=label,
                    text=text,
                )
            )
    return events


def episode_label(filename: str, script: str) -> str:
    match = re.search(r"(?im)^EPISODE NUMBER:\s*(.+?)\s*$", script)
    if match:
        return match.group(1).strip()
    match = re.search(r"episode[-_ ]?(\d+)", filename, re.IGNORECASE)
    return f"Episode {int(match.group(1))}" if match else filename


def build_prompt(episode: str, events: list[TimelineEvent]) -> str:
    timeline = [asdict(event) for event in events]
    return f"""You are helping a human editor find short social-media promos in a fictional microdrama screenplay.

Find up to 3 distinct, strong, continuous promo clips from {episode}. Each clip must be 20 to 60 seconds long. Favor an immediate hook (especially in the first 3 seconds), a clear unresolved cliffhanger, and enough context to make sense to a new viewer. Do not invent plot details or dialogue. Rank the best first.

Use only start and end timestamps that appear in the timeline below. The end timestamp must be later than the start timestamp. Give a concise hook, cliffhanger, and reason grounded in the script. score is an integer from 1 to 10. Return JSON only in this shape:
{{"promos":[{{"start_time":"00:00.00","end_time":"00:30.00","hook":"...","cliffhanger":"...","why_it_works":"...","score":8}}]}}

If no valid promo exists, return {{"promos":[]}}.

TIMELINE:
{json.dumps(timeline, ensure_ascii=False)}
"""


def build_batch_prompt(episodes: dict[str, list[TimelineEvent]]) -> str:
    timelines = {
        episode: [asdict(event) for event in events]
        for episode, events in episodes.items()
    }
    return f"""You are helping a human editor find short social-media promos in fictional microdrama screenplays.

Review all episodes below and find up to 3 distinct, strong, continuous promo clips per episode. Each clip must be 20 to 60 seconds long. Favor an immediate hook (especially in the first 3 seconds), a clear unresolved cliffhanger, and enough context to make sense to a new viewer. Do not invent plot details or dialogue.

Use only start and end timestamps from the named episode's timeline. Each promo must include the exact episode name shown as a JSON key below. Rank all returned promos by strength, best first. Give a concise hook, cliffhanger, and reason grounded in the script. score is an integer from 1 to 10. Return JSON only in this shape:
{{"promos":[{{"episode":"Episode 1","start_time":"00:00.00","end_time":"00:30.00","hook":"...","cliffhanger":"...","why_it_works":"...","score":8}}]}}

If no valid promo exists, return {{"promos":[]}}.

EPISODE TIMELINES:
{json.dumps(timelines, ensure_ascii=False)}
"""


def parse_model_result(
    raw_response: str, events: list[TimelineEvent]
) -> tuple[list[dict[str, Any]], list[str]]:
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    data = json.loads(cleaned)
    if not isinstance(data, dict) or not isinstance(data.get("promos"), list):
        raise ValueError("Gemini response must contain a 'promos' list.")

    boundaries = {event.start for event in events} | {event.end for event in events}
    accepted: list[dict[str, Any]] = []
    rejected: list[str] = []
    for index, promo in enumerate(data["promos"], start=1):
        reason = None
        if not isinstance(promo, dict):
            rejected.append(f"Promo {index}: response item was not an object.")
            continue
        start, end = promo.get("start_time"), promo.get("end_time")
        if start not in boundaries or end not in boundaries:
            reason = "start/end must match timestamps present in the script"
        else:
            duration = timestamp_to_seconds(end) - timestamp_to_seconds(start)
            if not 20 <= duration <= 60:
                reason = f"duration was {duration:.2f}s; expected 20–60s"
        for key in ("hook", "cliffhanger", "why_it_works"):
            if not isinstance(promo.get(key), str) or not promo[key].strip():
                reason = f"missing a usable {key}"
                break
        try:
            score = int(promo.get("score"))
            if not 1 <= score <= 10:
                raise ValueError
        except (TypeError, ValueError):
            reason = "score must be an integer from 1 to 10"

        if reason:
            rejected.append(f"Promo {index}: {reason}.")
            continue
        accepted.append(
            {
                "start_time": start,
                "end_time": end,
                "duration_seconds": round(duration, 2),
                "hook": promo["hook"].strip(),
                "cliffhanger": promo["cliffhanger"].strip(),
                "why_it_works": promo["why_it_works"].strip(),
                "score": score,
            }
        )
    return accepted, rejected


def parse_batch_model_result(
    raw_response: str, episodes: dict[str, list[TimelineEvent]]
) -> tuple[list[dict[str, Any]], list[str]]:
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    data = json.loads(cleaned)
    if not isinstance(data, dict) or not isinstance(data.get("promos"), list):
        raise ValueError("Gemini response must contain a 'promos' list.")

    grouped: dict[str, list[dict[str, Any]]] = {}
    rejected: list[str] = []
    for index, promo in enumerate(data["promos"], start=1):
        if not isinstance(promo, dict):
            rejected.append(f"Promo {index}: response item was not an object.")
            continue
        episode = promo.get("episode")
        if episode not in episodes:
            rejected.append(f"Promo {index}: episode did not match a submitted episode.")
            continue
        grouped.setdefault(episode, []).append(promo)

    accepted: list[dict[str, Any]] = []
    for episode, promos in grouped.items():
        validated, warnings = parse_model_result(
            json.dumps({"promos": promos}), episodes[episode]
        )
        for promo in validated:
            promo["episode"] = episode
            accepted.append(promo)
        rejected.extend(f"{episode}: {warning}" for warning in warnings)
    return accepted, rejected
