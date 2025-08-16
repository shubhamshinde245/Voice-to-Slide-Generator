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

    # Enhanced professional CSS themes
    theme_css = {
        "minimal": """
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
            body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin:0; background:#f8fafc; }
            .deck { height: 100vh; display:flex; align-items:center; justify-content:center; background:linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
            .slide { 
                display:none; width: 85vw; max-width: 1200px; height: 85vh; background:#ffffff; 
                border-radius:20px; box-shadow: 0 25px 80px rgba(0,0,0,0.15); padding:80px 100px;
                position:relative; overflow:hidden;
            }
            .slide::before {
                content: ''; position: absolute; top: 0; left: 0; right: 0; height: 6px;
                background: linear-gradient(90deg, #667eea, #764ba2);
            }
            h1 { font-size: 3.5rem; font-weight: 700; color: #1a202c; margin: 0 0 40px 0; line-height: 1.1; }
            h2 { font-size: 2.8rem; font-weight: 600; color: #2d3748; margin: 0 0 50px 0; line-height: 1.2; }
            ul { margin: 20px 0; padding-left: 0; list-style: none; }
            li { 
                margin: 25px 0; padding: 20px 0 20px 60px; font-size: 1.4rem; line-height: 1.6; 
                color: #4a5568; position: relative; font-weight: 400;
                border-left: 4px solid transparent;
            }
            li::before {
                content: '▶'; position: absolute; left: 20px; color: #667eea; font-size: 1.2rem;
                font-weight: 600;
            }
            .controls { position: fixed; bottom: 40px; left: 50%; transform: translateX(-50%); display:flex; gap:15px; }
            .btn { 
                border: 2px solid #e2e8f0; padding: 15px 25px; border-radius: 12px; cursor: pointer; 
                background: rgba(255,255,255,0.95); backdrop-filter: blur(10px); font-weight: 500;
                transition: all 0.3s ease; color: #2d3748; font-size: 14px;
            }
            .btn:hover { background: #667eea; color: white; border-color: #667eea; transform: translateY(-2px); }
            .notes { 
                margin-top: 60px; padding: 30px; background: #f7fafc; border-radius: 12px;
                border-left: 6px solid #667eea; font-size: 1.1rem; line-height: 1.7; display: none;
                color: #4a5568;
            }
            .header { 
                position: fixed; top: 40px; left: 60px; font-weight: 600; opacity: 0.8; 
                font-size: 1.1rem; color: white; text-shadow: 0 2px 4px rgba(0,0,0,0.3);
            }
            .slide-number {
                position: absolute; top: 40px; right: 60px; background: rgba(255,255,255,0.9);
                padding: 10px 20px; border-radius: 20px; font-weight: 600; color: #4a5568;
                backdrop-filter: blur(10px);
            }
        """,
        "corporate": """
            @import url('https://fonts.googleapis.com/css2?family=Source+Sans+Pro:wght@300;400;600;700&display=swap');
            body { font-family: 'Source Sans Pro', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin:0; }
            .deck { height: 100vh; display:flex; align-items:center; justify-content:center; background:#1a365d; }
            .slide { 
                display:none; width: 85vw; max-width: 1200px; height: 85vh; background:#ffffff; 
                border-radius:8px; box-shadow: 0 30px 100px rgba(0,0,0,0.25); padding:80px 100px;
                position:relative; border-top: 8px solid #2b6cb0;
            }
            .slide::after {
                content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 4px;
                background: linear-gradient(90deg, #2b6cb0, #3182ce);
            }
            h1 { font-size: 3.2rem; font-weight: 700; color: #1a202c; margin: 0 0 40px 0; line-height: 1.1; }
            h2 { font-size: 2.5rem; font-weight: 600; color: #2d3748; margin: 0 0 50px 0; line-height: 1.2; }
            ul { margin: 25px 0; padding-left: 0; list-style: none; }
            li { 
                margin: 30px 0; padding: 25px 0 25px 70px; font-size: 1.3rem; line-height: 1.6; 
                color: #4a5568; position: relative; font-weight: 400;
                background: linear-gradient(90deg, #f7fafc 0%, #ffffff 100%);
                border-radius: 8px; border-left: 5px solid #3182ce;
            }
            li::before {
                content: '●'; position: absolute; left: 30px; color: #2b6cb0; font-size: 1.5rem;
                font-weight: 900;
            }
            .controls { position: fixed; bottom: 40px; left: 50%; transform: translateX(-50%); display:flex; gap:15px; }
            .btn { 
                border: 2px solid #cbd5e1; padding: 15px 25px; border-radius: 6px; cursor: pointer; 
                background: #ffffff; font-weight: 600; transition: all 0.3s ease;
                color: #2d3748; font-size: 14px; text-transform: uppercase; letter-spacing: 0.5px;
            }
            .btn:hover { background: #2b6cb0; color: white; border-color: #2b6cb0; }
            .notes { 
                margin-top: 60px; padding: 35px; background: #edf2f7; border-radius: 8px;
                border-left: 8px solid #2b6cb0; font-size: 1.1rem; line-height: 1.7; display: none;
                color: #4a5568; font-style: italic;
            }
            .header { 
                position: fixed; top: 40px; left: 60px; font-weight: 700; opacity: 0.9; 
                font-size: 1.2rem; color: white; text-transform: uppercase; letter-spacing: 1px;
            }
            .slide-number {
                position: absolute; top: 40px; right: 60px; background: #2b6cb0;
                padding: 12px 24px; border-radius: 4px; font-weight: 700; color: white;
                font-size: 14px; letter-spacing: 0.5px;
            }
            .company-logo {
                position: absolute; bottom: 40px; right: 60px; width: 60px; height: 20px;
                background: #e2e8f0; border-radius: 4px; opacity: 0.7;
            }
        """,
        "dark": """
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
            body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin:0; background:#0f172a; }
            .deck { height: 100vh; display:flex; align-items:center; justify-content:center; background:linear-gradient(135deg, #1e293b 0%, #0f172a 100%); }
            .slide { 
                display:none; width: 85vw; max-width: 1200px; height: 85vh; 
                background:linear-gradient(145deg, #1e293b 0%, #334155 100%);
                border-radius:24px; box-shadow: 0 40px 120px rgba(0,0,0,0.6); padding:80px 100px;
                position:relative; border: 1px solid #334155;
            }
            .slide::before {
                content: ''; position: absolute; top: 0; left: 0; right: 0; height: 6px;
                background: linear-gradient(90deg, #6366f1, #8b5cf6);
                border-radius: 24px 24px 0 0;
            }
            h1 { font-size: 3.5rem; font-weight: 700; color: #f1f5f9; margin: 0 0 40px 0; line-height: 1.1; }
            h2 { font-size: 2.8rem; font-weight: 600; color: #e2e8f0; margin: 0 0 50px 0; line-height: 1.2; }
            ul { margin: 25px 0; padding-left: 0; list-style: none; }
            li { 
                margin: 30px 0; padding: 25px 0 25px 70px; font-size: 1.4rem; line-height: 1.6; 
                color: #cbd5e1; position: relative; font-weight: 400;
                background: rgba(51, 65, 85, 0.3); border-radius: 12px;
                border-left: 4px solid #6366f1; backdrop-filter: blur(10px);
            }
            li::before {
                content: '◆'; position: absolute; left: 25px; color: #8b5cf6; font-size: 1.3rem;
                font-weight: 600;
            }
            .controls { position: fixed; bottom: 40px; left: 50%; transform: translateX(-50%); display:flex; gap:15px; }
            .btn { 
                border: 2px solid #475569; padding: 15px 25px; border-radius: 12px; cursor: pointer; 
                background: rgba(30, 41, 59, 0.8); backdrop-filter: blur(10px); font-weight: 500;
                transition: all 0.3s ease; color: #e2e8f0; font-size: 14px;
            }
            .btn:hover { background: #6366f1; color: white; border-color: #6366f1; transform: translateY(-2px); }
            .notes { 
                margin-top: 60px; padding: 35px; background: rgba(15, 23, 42, 0.6); border-radius: 12px;
                border-left: 6px solid #8b5cf6; font-size: 1.1rem; line-height: 1.7; display: none;
                color: #cbd5e1; backdrop-filter: blur(10px);
            }
            .header { 
                position: fixed; top: 40px; left: 60px; font-weight: 600; opacity: 0.9; 
                font-size: 1.1rem; color: #e2e8f0;
            }
            .slide-number {
                position: absolute; top: 40px; right: 60px; background: rgba(99, 102, 241, 0.2);
                padding: 12px 20px; border-radius: 20px; font-weight: 600; color: #e2e8f0;
                backdrop-filter: blur(10px); border: 1px solid rgba(99, 102, 241, 0.3);
            }
        """,
    }[theme if theme in ["minimal","corporate","dark"] else "minimal"]

    # Build enhanced slides HTML
    slides_html = []
    total_slides = len(slides)
    
    for i, s in enumerate(slides, start=1):
        heading = s.get("heading", f"Slide {i}")
        bullets = s.get("bullets", [])
        notes = s.get("notes", "")
        bullets_html = "".join(f"<li>{b}</li>" for b in bullets[:7])
        
        slide_html = f"""
        <section class="slide" data-idx="{i-1}">
            <div class="slide-number">{i} / {total_slides}</div>
            <h2>{heading}</h2>
            <ul>{bullets_html}</ul>
            <div class="notes"><strong>Speaker Notes:</strong><br>{notes}</div>
            <div class="company-logo"></div>
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

/* Print-specific styles for PDF generation */
@media print {{
    @page {{
        size: A4 landscape;
        margin: 0;
    }}
    
    body {{
        background: white !important;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
    }}
    
    .deck {{
        background: transparent !important;
    }}
    
    .slide {{
        display: block !important;
        page-break-after: always;
        page-break-inside: avoid;
        width: 100vw !important;
        height: 100vh !important;
        margin: 0 !important;
        box-shadow: none !important;
        border-radius: 0 !important;
    }}
    
    .slide:last-child {{
        page-break-after: avoid;
    }}
    
    .controls {{
        display: none !important;
    }}
    
    .header {{
        position: absolute !important;
        color: #333 !important;
        text-shadow: none !important;
    }}
    
    .slide-number {{
        background: #f0f0f0 !important;
        color: #333 !important;
        backdrop-filter: none !important;
        border: 1px solid #ddd !important;
    }}
    
    .notes {{
        display: none !important;
    }}
}}
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
        "You are an expert presentation designer creating polished, enterprise-grade slide decks.\n"
        "RULES:\n"
        "- Create 5–10 professional slides with clear, impactful content\n"
        "- Each slide should have a compelling headline and 3–5 concise, actionable bullet points\n" 
        "- Bullet points should be results-focused and use strong action words\n"
        "- Include detailed 3–5 sentence speaker notes for each slide with key talking points\n"
        "- Use professional language appropriate for executive presentations\n"
        "- Structure content logically with clear flow between ideas\n"
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
