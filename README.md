# Microdrama Promo Finder

A Streamlit prototype that asks Gemini to suggest promo moments from timestamped screenplay `.txt` files. Code validates that returned clip boundaries exist in the source timeline and that each clip is 20–60 seconds long.

## Run locally

1. Use Python 3.10 or later.
2. In this directory, run `python -m pip install -r requirements.txt`.
3. Configure `GEMINI_API_KEY` as a local environment variable or in `.streamlit/secrets.toml`:

   ```toml
   GEMINI_API_KEY = "your-key"
   ```

   The key is not entered in the app UI and must not be committed to Git.
4. Run `streamlit run app.py`.
5. Upload the folder containing the `.txt` episode files. The app sorts files by episode number and processes up to 50 by default. You can also select multiple individual `.txt` files.

Episodes are grouped into Gemini requests (five per request by default), reducing 50 episodes to about 10 calls. Calls are spaced by 13 seconds to stay within the example free-tier limit of five requests per minute, and temporary 429/503 errors are retried. A full-pack run can still take a few minutes or longer depending on Gemini response time. Actual quotas vary by account and model. Valid candidates from all successfully processed episodes are ranked together.

The app does not bundle the assignment's scripts. The script folder is excluded from Git; do not publish or share Kuku's input pack.

## Deploy on Streamlit Community Cloud

1. Create a GitHub repository containing `app.py`, `promo_core.py`, `requirements.txt`, and this README.
2. Confirm the screenplay input-pack folder is not in the repository.
3. In Streamlit Community Cloud, deploy that repository and set the main file to `app.py`.
4. In Streamlit Community Cloud, open the app's **Settings → Secrets** and add:

   ```toml
   GEMINI_API_KEY = "your-key"
   ```

5. Open the deployed app and test with a short, authorized sample before uploading assignment scripts.

The app can be publicly accessible, but your Gemini key stays server-side in Streamlit Secrets and is not shown to visitors. Anyone who can access the public app may use your configured Gemini quota by uploading scripts and running it. For an assignment demo, restrict access if available or only share the URL with intended reviewers; monitor API usage and set provider-side spending/usage limits. Do not put the key in source code or a public repository. Uploaded script contents are sent to Gemini by this prototype; check the provider's data terms and use only content you are permitted to process.

## Current scope

- One continuous promo segment per candidate; no video editing or stitched segments.
- Upload a folder of episodes; up to three candidates per episode are ranked together using Gemini's 1–10 score.
- A human should review every suggestion. Model scores are not an objective quality metric.
- JSON download includes the raw model response and any validation warnings.
