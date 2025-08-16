import os
import io
import re
import json
import base64
from typing import Any, Dict, List

import streamlit as st
import streamlit.components.v1 as components
from audio_recorder_streamlit import audio_recorder

# --- OpenAI SDK v1 style ---
try:
    from openai import OpenAI
except Exception:
    OpenAI = None


# ---------------------------
# App Config
# ---------------------------
st.set_page_config(
    page_title="Voice → Slide Generator",
    page_icon="🎤",
    layout="wide",
)

st.title("🎤 Voice → Slide Generator")
st.caption("Speak for up to ~3 minutes. Get a polished slide deck (HTML) with speaker notes.")

# ---------------------------
# Secrets / Env
# ---------------------------
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
OPENAI_CHAT_MODEL = st.secrets.get("OPENAI_CHAT_MODEL") or os.getenv("OPENAI_CHAT_MODEL") or "gpt-4o-mini"
WHISPER_MODEL = "whisper-1"

if not OPENAI_API_KEY:
    st.warning("Add your OpenAI key in `.streamlit/secrets.toml` or Streamlit Cloud → Settings → Secrets (OPENAI_API_KEY).", icon="⚠️")

# Instantiate client if possible
client = None
if OPENAI_API_KEY and OpenAI is not None:
    client = OpenAI(api_key=OPENAI_API_KEY)


# ---------------------------
# Sidebar Controls
# ---------------------------
with st.sidebar:
    st.header("⚙️ Settings")
    theme = st.selectbox("Theme", ["minimal", "corporate", "dark"], index=0)
    tone = st.selectbox("Tone", ["Pitch", "Educational", "Report"], index=0)
    n_slides = st.slider("Slide count", min_value=5, max_value=10, value=6, step=1)
    temperature = st.slider("Creativity (temperature)", min_value=0.2, max_value=0.8, value=0.5, step=0.1)
    st.markdown("---")
    st.markdown("**Privacy**: Audio is processed to create slides and then discarded. Nothing is persisted server-side.")
    if st.button("🧹 Clear session"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.experimental_rerun()


# ---------------------------
# Helpers
# ---------------------------
def extract_json(text: str) -> Dict[str, Any]:
    """
    Extract the first valid JSON object from a string (tolerates code fences).
    """
    # Remove code fences if present
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE)
    # Find first {...} block heuristically
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        raise ValueError("No JSON object found.")
    raw = m.group(0)
    return json.loads(raw)


def coerce_deck(deck: Dict[str, Any], min_slides: int = 5) -> Dict[str, Any]:
    """
    Ensure required keys exist and minimum slide count is met.
    """
    deck.setdefault("title", "Generated Presentation")
    deck.setdefault("theme", "minimal")
    deck.setdefault("slides", [])
    if not isinstance(deck["slides"], list):
        deck["slides"] = []

    # Pad slides if fewer than required
    while len(deck["slides"]) < min_slides:
        deck["slides"].append({
            "heading": f"Slide {len(deck['slides'])+1}",
            "bullets": ["Point A", "Point B", "Point C"],
            "notes": "Speaker notes for this slide."
        })
    return deck


def build_html(deck: Dict[str, Any]) -> str:
    """
    Build a single-file, offline HTML deck with simple navigation and speaker notes.
    No external CDN dependencies.
    """
    title = deck.get("title", "Presentation")
    slides = deck.get("slides", [])
    theme = deck.get("theme", "minimal")

    # Minimal CSS themes
    theme_css = {
        "minimal": """
            body { font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin:0; }
            .deck { height: 100vh; display:flex; align-items:center; justify-content:center; background:#fafafa; color:#111; }
            .slide { display:none; width: 80vw; height: 80vh; background:#fff; border-radius:16px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); padding:48px; }
            h1,h2 { margin:0 0 16px 0; }
            ul { margin:12px 0 0 18px; }
            .controls { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); display:flex; gap:8px; }
            .btn { border:1px solid #ddd; padding:10px 14px; border-radius:10px; cursor:pointer; background:#fff; }
            .btn:active { transform: translateY(1px); }
            .notes { margin-top: 16px; padding: 12px; border-left: 4px solid #eee; background:#f7f7f7; display:none; }
            .header { position: fixed; top: 16px; left: 24px; font-weight: 600; opacity:.7; }
        """,
        "corporate": """
            body { font-family: Segoe UI, system-ui, -apple-system, Roboto, Arial, sans-serif; margin:0; }
            .deck { height: 100vh; display:flex; align-items:center; justify-content:center; background:#f0f3f7; color:#1f2d3d; }
            .slide { display:none; width: 82vw; height: 80vh; background:#fff; border-radius:12px; box-shadow: 0 16px 40px rgba(0,0,0,0.12); padding:52px; border: 1px solid #e6eaf0;}
            h1,h2 { margin:0 0 16px 0; color:#0f172a; }
            ul { margin:12px 0 0 18px; }
            .controls { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); display:flex; gap:8px; }
            .btn { border:1px solid #cbd5e1; padding:10px 14px; border-radius:10px; cursor:pointer; background:#ffffff; }
            .btn:active { transform: translateY(1px); }
            .notes { margin-top: 16px; padding: 12px; border-left: 4px solid #cbd5e1; background:#eef2f7; display:none; }
            .header { position: fixed; top: 16px; left: 24px; font-weight: 700; opacity:.7; }
        """,
        "dark": """
            body { font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin:0; background:#0b0f17; color:#e6e6e6; }
            .deck { height: 100vh; display:flex; align-items:center; justify-content:center; }
            .slide { display:none; width: 82vw; height: 80vh; background:#121826; border-radius:16px; box-shadow: 0 16px 40px rgba(0,0,0,0.45); padding:52px; border: 1px solid #1f2a44;}
            h1,h2 { margin:0 0 16px 0; color:#f5f7fb; }
            ul { margin:12px 0 0 18px; }
            .controls { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); display:flex; gap:8px; }
            .btn { border:1px solid #243049; padding:10px 14px; border-radius:10px; cursor:pointer; background:#0f172a; color:#e6e6e6; }
            .btn:active { transform: translateY(1px); }
            .notes { margin-top: 16px; padding: 12px; border-left: 4px solid #243049; background:#0f172a; display:none; }
            .header { position: fixed; top: 16px; left: 24px; font-weight: 700; opacity:.6; }
        """,
    }[theme if theme in ["minimal","corporate","dark"] else "minimal"]

    # Build slides HTML
    slides_html = []
    for i, s in enumerate(slides, start=1):
        heading = s.get("heading", f"Slide {i}")
        bullets = s.get("bullets", [])
        notes = s.get("notes", "")
        bullets_html = "".join(f"<li>{b}</li>" for b in bullets[:7])
        slide_html = f"""
        <section class="slide" data-idx="{i-1}">
            <h2>{heading}</h2>
            <ul>{bullets_html}</ul>
            <div class="notes"><strong>Speaker notes:</strong> {notes}</div>
        </section>
        """
        slides_html.append(slide_html)

    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title}</title>
<style>
{theme_css}
</style>
</head>
<body>
<div class="header">{title}</div>
<div class="deck">
  {''.join(slides_html)}
</div>
<div class="controls">
  <button class="btn" onclick="prev()">◀ Prev</button>
  <button class="btn" onclick="next()">Next ▶</button>
  <button class="btn" onclick="toggleNotes()">🗒 Notes</button>
</div>
<script>
let idx = 0;
const slides = Array.from(document.querySelectorAll('.slide'));
function show(i) {{
  slides.forEach(s => s.style.display = 'none');
  idx = (i + slides.length) % slides.length;
  slides[idx].style.display = 'block';
}}
function next() {{ show(idx + 1); }}
function prev() {{ show(idx - 1); }}
function toggleNotes() {{
  const s = slides[idx].querySelector('.notes');
  if (s) s.style.display = (s.style.display === 'none' || !s.style.display) ? 'block' : 'none';
}}
document.addEventListener('keydown', (e) => {{
  if (e.key === 'ArrowRight') next();
  if (e.key === 'ArrowLeft') prev();
  if (e.key.toLowerCase() === 'n') toggleNotes();
}});
show(0);
</script>
</body>
</html>
    """.strip()
    return html


def b64_download(data: bytes, filename: str, mime: str) -> str:
    b64 = base64.b64encode(data).decode()
    return f"data:{mime};base64,{b64}", b64


def transcribe_audio(file_path: str) -> str:
    if not client:
        raise RuntimeError("OpenAI client not initialized. Add OPENAI_API_KEY.")
    with open(file_path, "rb") as f:
        # OpenAI SDK v1
        tr = client.audio.transcriptions.create(
            model=WHISPER_MODEL,
            file=f
        )
    # Some SDK versions return .text, others may differ; normalize
    text = getattr(tr, "text", None)
    if not text and isinstance(tr, dict):
        text = tr.get("text")
    if not text:
        raise RuntimeError("Transcription returned no text.")
    return text


def generate_deck_json(transcript: str, theme: str, tone: str, n_slides: int, temperature: float) -> Dict[str, Any]:
    if not client:
        raise RuntimeError("OpenAI client not initialized. Add OPENAI_API_KEY.")
    system = (
        "You are a slide generator. Convert the user's transcript into a concise slide deck.\n"
        "RULES: 5–10 slides; each slide has 3–5 bullets and 2–6 sentence speaker notes.\n"
        "OUTPUT: JSON matching the schema exactly. No markdown, no commentary."
    )
    schema_hint = """
{
  "title": "string",
  "theme": "minimal|corporate|dark",
  "slides": [
    { "heading": "string", "bullets": ["string", "string"], "notes": "string" }
  ]
}
""".strip()

    user = f"""
TRANSCRIPT:
{transcript}

STYLE:
Tone={tone} | Theme={theme} | SlideCount={n_slides}

Return ONLY valid JSON (no backticks). Schema:
{schema_hint}
""".strip()

    resp = client.chat.completions.create(
        model=OPENAI_CHAT_MODEL,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]
    )
    content = resp.choices[0].message.content
    data = extract_json(content)
    return coerce_deck(data, min_slides=5)


# ---------------------------
# UI — Step 1: Audio Ingestion
# ---------------------------
st.subheader("1) Upload or Record Audio (≤ ~3 minutes recommended)")
col1, col2 = st.columns(2, gap="large")

with col1:
    st.write("**Upload** (.wav, .mp3, .m4a)")
    uploaded = st.file_uploader("Choose an audio file", type=["wav", "mp3", "m4a"])

with col2:
    st.write("**Record** (click to start/stop)")
    audio_bytes = audio_recorder(
        text="",
        recording_color="#e11d48",
        neutral_color="#0ea5e9",
        icon_name="microphone",
        icon_size="2x",
    )
    # audio_recorder returns WAV bytes if recorded

audio_path = None
if uploaded is not None:
    suffix = os.path.splitext(uploaded.name)[1] or ".wav"
    audio_path = os.path.join(st.experimental_get_query_params().get("tmpdir", ["."])[0], f"_upload{suffix}")
    with open(audio_path, "wb") as f:
        f.write(uploaded.read())
elif audio_bytes:
    audio_path = "_recorded.wav"
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)

if audio_path:
    st.audio(audio_path)
else:
    st.info("Upload a file or record audio to continue.", icon="ℹ️")


# ---------------------------
# UI — Step 2: Transcribe
# ---------------------------
st.subheader("2) Transcribe")
if st.button("📝 Transcribe Audio", disabled=not audio_path):
    if not client:
        st.error("OpenAI client not initialized. Add OPENAI_API_KEY.", icon="⚠️")
    else:
        with st.spinner("Transcribing…"):
            try:
                transcript = transcribe_audio(audio_path)
                st.session_state["transcript"] = transcript
            except Exception as e:
                st.error(f"Transcription failed: {e}")

transcript_text = st.session_state.get("transcript", "")
transcript_text = st.text_area("Transcript (editable)", value=transcript_text, height=200, placeholder="Your transcript will appear here…")
st.session_state["transcript"] = transcript_text.strip()

# ---------------------------
# UI — Step 3: Generate Deck
# ---------------------------
st.subheader("3) Generate Slide Deck")
gen_col1, gen_col2 = st.columns([1,1])
with gen_col1:
    generate_clicked = st.button("✨ Generate Deck", disabled=not st.session_state.get("transcript"))
with gen_col2:
    regen_clicked = st.button("🔁 Regenerate (keep transcript)", disabled=not st.session_state.get("transcript"))

if generate_clicked or regen_clicked:
    if not client:
        st.error("OpenAI client not initialized. Add OPENAI_API_KEY.", icon="⚠️")
    else:
        with st.spinner("Creating deck…"):
            try:
                deck = generate_deck_json(
                    transcript=st.session_state["transcript"],
                    theme=theme,
                    tone=tone,
                    n_slides=n_slides,
                    temperature=temperature
                )
                st.session_state["deck"] = deck
                html = build_html(deck)
                st.session_state["html"] = html
            except Exception as e:
                st.error(f"Deck generation failed: {e}")

# ---------------------------
# UI — Step 4: Preview & Download
# ---------------------------
deck = st.session_state.get("deck")
html = st.session_state.get("html")

if deck and html:
    st.subheader("4) Preview")
    components.html(html, height=700, scrolling=True)

    st.subheader("5) Download")
    html_bytes = html.encode("utf-8")
    st.download_button("💾 Download HTML Deck", data=html_bytes, file_name="deck.html", mime="text/html")

    # Also offer raw JSON + transcript for editing offline
    st.download_button("💾 Download JSON (slides)", data=json.dumps(deck, indent=2).encode("utf-8"),
                       file_name="deck.json", mime="application/json")
    if st.session_state.get("transcript"):
        st.download_button("💾 Download Transcript (.txt)", data=st.session_state["transcript"].encode("utf-8"),
                           file_name="transcript.txt", mime="text/plain")

    st.info("Tip: Open the HTML deck and **Print to PDF** in your browser to create a PDF version.", icon="💡")
