# Microdrama Promo Finder

A Streamlit prototype that asks Sarvam's `glm5.3-flash` model to suggest promo moments from timestamped screenplay `.txt` files. Code validates that returned clip boundaries exist in the source timeline and that each clip is 20–60 seconds long.

## Run locally

1. Use Python 3.10 or later.
2. In this directory, run `python -m pip install -r requirements.txt`.
3. Configure `SARVAM_API_KEY` as a local environment variable or in `.streamlit/secrets.toml`:

   ```toml
   SARVAM_API_KEY = "your-key"
   ```

   The key is not entered in the app UI and must not be committed to Git.
4. Run `streamlit run app.py`.
5. Upload the folder containing the `.txt` episode files. The app sorts files by episode number and processes up to 50 by default. You can also select multiple individual `.txt` files.

All selected episodes are sent together in one Sarvam request, so a full-pack run uses one API call rather than 50. The supplied 50-script prompt is about 593,000 characters (~148K tokens by a rough estimate). The default `glm5.3-flash` model has a documented 1M-token context window, but latency, account limits, and output limits still apply. The app displays prompt size and reports API errors. Temporary 429/503 errors are retried. Valid candidates are ranked together across episodes.

The app does not bundle the assignment's scripts. The script folder is excluded from Git; do not publish or share Kuku's input pack.

## Deploy on Streamlit Community Cloud

1. Create a GitHub repository containing `app.py`, `promo_core.py`, `requirements.txt`, and this README.
2. Confirm the screenplay input-pack folder is not in the repository.
3. In Streamlit Community Cloud, deploy that repository and set the main file to `app.py`.
4. In Streamlit Community Cloud, open the app's **Settings → Secrets** and add:

   ```toml
   SARVAM_API_KEY = "your-key"
   ```

5. Open the deployed app and test with a short, authorized sample before uploading assignment scripts.

The app can be publicly accessible, but your Sarvam key stays server-side in Streamlit Secrets and is not shown to visitors. Anyone who can access the public app may use your configured quota by uploading scripts and running it. For an assignment demo, only share the URL with intended reviewers; monitor API usage. Do not put the key in source code or a public repository. Uploaded script contents are sent to Sarvam by this prototype; check the provider's data terms and use only content you are permitted to process.

## Current scope

- One continuous promo segment per candidate; no video editing or stitched segments.
- Upload a folder of episodes; up to three candidates per episode are ranked together using the model's 1–10 score.
- A human should review every suggestion. Model scores are not an objective quality metric.
- JSON download includes the raw model response and any validation warnings.
