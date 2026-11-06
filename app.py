import json
import os
import re
from datetime import datetime, timezone

import streamlit as st

from promo_core import (
    build_batch_prompt,
    call_with_retries,
    episode_label,
    parse_batch_model_result,
    parse_timeline,
)


st.set_page_config(page_title="Promo Finder", page_icon="🎬", layout="wide")
st.title("🎬 Microdrama Promo Finder")
st.caption(
    "Upload screenplay .txt files to shortlist promo moments. Gemini suggests candidates; "
    "timestamp and duration checks are enforced in code."
)


def configured_api_key() -> str:
    try:
        return st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
    except FileNotFoundError:
        return os.getenv("GEMINI_API_KEY", "")


def episode_sort_key(uploaded_file):
    match = re.search(r"episode[-_ ]?(\d+)", uploaded_file.name, re.IGNORECASE)
    return (
        int(match.group(1)) if match else float("inf"),
        uploaded_file.name.lower(),
    )


api_key = configured_api_key()
with st.sidebar:
    st.header("Settings")
    if api_key:
        st.success("Gemini API configured")
    else:
        st.warning("Gemini API key is not configured.")
    model_name = st.text_input("Gemini model", value="gemini-3.8-flash")
    max_episodes = st.number_input(
        "Maximum episodes to process per run", min_value=1, max_value=50, value=50
    )
    st.caption("All selected episodes are analyzed together in one Gemini request.")

uploads = st.file_uploader(
    "Choose the folder containing episode screenplay files",
    type=["txt"],
    accept_multiple_files="directory",
    help="Select the folder with the 50 episode .txt files. You can also select multiple .txt files.",
)

if uploads:
    st.info(
        f"{len(uploads)} episode file(s) selected. The app processes up to "
        f"{int(max_episodes)} episodes in this run."
    )

if st.button("Find promos in one request", type="primary", disabled=not uploads):
    if not api_key:
        st.error(
            "The app owner must configure GEMINI_API_KEY in Streamlit Secrets "
            "or as a local environment variable."
        )
        st.stop()
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        st.error("Gemini SDK is missing. Install dependencies from requirements.txt.")
        st.exception(exc)
        st.stop()

    client = genai.Client(api_key=api_key)
    selected_uploads = sorted(uploads, key=episode_sort_key)[: int(max_episodes)]
    episode_events = {}
    source_by_episode = {}
    failures = []
    progress = st.progress(0, text="Preparing scripts…")

    for uploaded_file in selected_uploads:
        script = uploaded_file.getvalue().decode("utf-8-sig", errors="replace")
        label = episode_label(uploaded_file.name, script)
        events = parse_timeline(script)
        if not events:
            failures.append(
                {"file": uploaded_file.name, "error": "No timestamped screenplay events found."}
            )
            continue
        episode_events[label] = events
        source_by_episode[label] = uploaded_file.name

    raw_response = ""
    validation_warnings = []
    promos_by_episode = {episode: [] for episode in episode_events}
    if episode_events:
        try:
            prompt = build_batch_prompt(episode_events)
            prompt_chars = len(prompt)
            progress.progress(
                0.1,
                text=(
                    f"Sending one request for {len(episode_events)} episodes "
                    f"({prompt_chars:,} prompt characters). Gemini may take a while."
                ),
            )
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            )
            response = call_with_retries(
                lambda: client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
            )
            raw_response = response.text or ""
            promos, validation_warnings = parse_batch_model_result(
                raw_response, episode_events
            )
            for promo in promos:
                promo["source_file"] = source_by_episode[promo["episode"]]
                promos_by_episode[promo["episode"]].append(promo)
        except Exception as exc:
            failures.extend(
                {
                    "file": source_by_episode[episode],
                    "error": f"{type(exc).__name__}: {exc}",
                }
                for episode in episode_events
            )

    results = [
        {
            "episode": episode,
            "source_file": source_by_episode[episode],
            "promos": promos_by_episode[episode],
            "validation_warnings": validation_warnings,
        }
        for episode in episode_events
    ]
    progress.progress(1.0, text="Analysis finished.")

    ranked = sorted(
        (promo for result in results for promo in result["promos"]),
        key=lambda promo: promo["score"],
        reverse=True,
    )
    st.session_state["promo_run"] = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": model_name,
        "results": results,
        "ranked_promos": ranked,
        "failures": failures,
        "raw_model_response": raw_response,
    }

run = st.session_state.get("promo_run")
if run:
    st.subheader("Ranked promo candidates")
    if not run["ranked_promos"]:
        st.warning("No valid promo candidates were returned in this run.")
    for rank, promo in enumerate(run["ranked_promos"], start=1):
        with st.expander(
            f"#{rank} · {promo['episode']} · {promo['start_time']}–{promo['end_time']} "
            f"({promo['duration_seconds']}s) · score {promo['score']}/10",
            expanded=rank == 1,
        ):
            st.markdown(f"**Hook:** {promo['hook']}")
            st.markdown(f"**Cliffhanger:** {promo['cliffhanger']}")
            st.markdown(f"**Why it works:** {promo['why_it_works']}")

    for warning in dict.fromkeys(
        warning
        for result in run["results"]
        for warning in result["validation_warnings"]
    ):
        st.warning(warning)
    if run["failures"]:
        st.subheader("Files that could not be processed")
        st.json(run["failures"])

    raw_outputs = json.dumps(run, ensure_ascii=False, indent=2)
    st.download_button(
        "Download raw run output (JSON)",
        data=raw_outputs,
        file_name="promo_finder_raw_outputs.json",
        mime="application/json",
    )

st.divider()
st.caption(
    "Prototype limits: currently finds single continuous segments, not stitched multi-episode "
    "promos. Always review candidates manually. Uploaded screenplay text is sent to Google "
    "Gemini for analysis; use only inputs you are authorized to process."
)
