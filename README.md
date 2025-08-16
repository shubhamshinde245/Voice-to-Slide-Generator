# Voice → Slide Generator (Streamlit)

Turn a ≤3 minute spoken prompt into a polished slide deck (HTML with speaker notes).  
**MVP exports:** single-file HTML (print to PDF via browser).

## Quick Start (Local)
1. `python -m venv .venv && source .venv/bin/activate` (Windows: `.venv\Scripts\activate`)
2. `pip install -r requirements.txt`
3. Put your OpenAI key in `.streamlit/secrets.toml` → `OPENAI_API_KEY`
4. `streamlit run streamlit_app.py`

## On Streamlit Community Cloud
- Deploy this repo.
- In **Settings → Secrets**, add:
  - `OPENAI_API_KEY`: your key
  - (Optional) `OPENAI_CHAT_MODEL`: e.g. `gpt-4o-mini`
- Set the main file to `streamlit_app.py`.

## Features
- Upload **or** record audio
- Whisper API transcription
- LLM-generated deck (5–10 slides) with speaker notes
- In-app preview + download **HTML** deck (single file)
- Browser **Print to PDF** supported

## Notes
- Keep audio ≲ 3 minutes for speed and cost.
- If JSON parsing fails (rare), the app coerces output and pads to ≥5 slides.
