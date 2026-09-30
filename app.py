# app.py
import io
import os
import json
import time
import sqlite3
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
from streamlit_mic_recorder import speech_to_text
from groq import Groq
from database import init_db, get_dynamic_schema_summary, run_query, load_csv_to_db

# 1. Page Configuration
st.set_page_config(
    page_title="QuerySpeak // Voice SQL Studio",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

init_db()

# 2. Session State Initialization
if "audit_history" not in st.session_state:
    st.session_state.audit_history = []
if "last_query" not in st.session_state:
    st.session_state.last_query = ""

# 3. Modern Glassmorphic Dark UI Styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }

    .stApp {
        background-color: #0b0f19;
        background-image: 
            radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.12) 0px, transparent 50%),
            radial-gradient(at 100% 0%, rgba(14, 165, 233, 0.10) 0px, transparent 50%),
            radial-gradient(at 50% 100%, rgba(15, 23, 42, 0.8) 0px, transparent 100%);
        color: #e2e8f0;
    }

    .brand-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: rgba(15, 23, 42, 0.65);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 18px 24px;
        backdrop-filter: blur(16px);
        margin-bottom: 24px;
    }

    .brand-title {
        font-size: 26px;
        font-weight: 700;
        background: linear-gradient(135deg, #38bdf8 0%, #818cf8 50%, #c084fc 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.5px;
        margin: 0;
    }

    .console-card {
        background: rgba(15, 23, 42, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.07);
        border-radius: 14px;
        padding: 20px;
        backdrop-filter: blur(12px);
        margin-bottom: 20px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.36);
    }

    .badge-chip {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 11px;
        font-weight: 600;
        padding: 4px 10px;
        border-radius: 6px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .badge-live {
        background: rgba(16, 185, 129, 0.12);
        color: #34d399;
        border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .badge-info {
        background: rgba(99, 102, 241, 0.12);
        color: #a5b4fc;
        border: 1px solid rgba(99, 102, 241, 0.3);
    }

    .explanation-box {
        background: rgba(99, 102, 241, 0.08);
        border-left: 3px solid #818cf8;
        padding: 12px 16px;
        border-radius: 0 8px 8px 0;
        margin: 12px 0;
        font-size: 14px;
        color: #cbd5e1;
    }

    .stTextInput>div>div>input {
        background: rgba(2, 6, 23, 0.8) !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        border-radius: 10px !important;
        color: #f8fafc !important;
        font-size: 14px !important;
        padding: 12px 16px !important;
    }
    .stTextInput>div>div>input:focus {
        border-color: #38bdf8 !important;
        box-shadow: 0 0 12px rgba(56, 189, 248, 0.35) !important;
    }

    .stButton>button {
        background: linear-gradient(135deg, #0284c7 0%, #4f46e5 100%) !important;
        color: #ffffff !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        padding: 10px 22px !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease !important;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(79, 70, 229, 0.45) !important;
    }

    code, pre {
        font-family: 'JetBrains Mono', monospace !important;
    }
</style>
""", unsafe_allow_html=True)

# 4. Browser Native Text-to-Speech Helper
def trigger_tts(text_to_speak: str):
    clean_text = text_to_speak.replace('"', '\\"').replace("'", "\\'")
    tts_html = f"""
    <script>
        if ('speechSynthesis' in window) {{
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance("{clean_text}");
            utterance.rate = 1.05;
            utterance.pitch = 1.0;
            utterance.lang = 'en-US';
            window.speechSynthesis.speak(utterance);
        }}
    </script>
    """
    components.html(tts_html, height=0, width=0)

# 5. Authentication & Groq Setup
groq_key = st.secrets.get("GROQ_API_KEY", os.getenv("GROQ_API_KEY"))
if not groq_key:
    groq_key = st.sidebar.text_input("Groq API Key", type="password")

if not groq_key:
    st.info("👋 Enter your Groq API Key in the sidebar or via secrets to access the query engine.")
    st.stop()

client = Groq(api_key=groq_key)

@st.cache_resource
def get_available_groq_models():
    try:
        models = client.models.list().data
        active = [m.id for m in models if not any(x in m.id for x in ["whisper", "guard", "vision", "orpheus"])]
        return active if active else ["llama-3.1-8b-instant"]
    except Exception:
        return ["llama-3.1-8b-instant"]

available_models = get_available_groq_models()

# 6. Sidebar: Custom Dataset Ingestion & Architecture
with st.sidebar:
    st.markdown("### 🗄️ Dataset & Tables")
    st.caption("Active Database: `queryspeak.db` (SQLite)")

    # Custom CSV Ingestion
    with st.expander("📤 Ingest Custom CSV", expanded=False):
        uploaded_csv = st.file_uploader("Upload dataset (.csv)", type=["csv"])
        custom_tbl_name = st.text_input("Assign Table Name", value="custom_data")
        if uploaded_csv and st.button("Load Table to DB"):
            tbl_name, row_cnt, cols = load_csv_to_db(uploaded_csv, custom_tbl_name)
            st.success(f"Ingested `{tbl_name}` ({row_cnt} rows, {len(cols)} columns)!")

    # Live Schema Explorer
    with st.expander("🧭 Live Schema Explorer", expanded=True):
        st.code(get_dynamic_schema_summary(), language="text")

    st.markdown("---")
    st.markdown("**Engine Model:**")
    st.caption(f"`{available_models[0]}`")

    # Audit Trail
    with st.expander(f"📜 Audit History ({len(st.session_state.audit_history)})", expanded=False):
        if not st.session_state.audit_history:
            st.caption("No queries executed yet.")
        else:
            for item in reversed(st.session_state.audit_history[-8:]):
                st.markdown(f"**Prompt:** {item['prompt']}")
                st.code(item['sql'], language="sql")
                st.caption(f"⚡ {item['latency']}s | 📊 {item['rows']} rows")
                st.markdown("---")

# 7. Main Header
st.markdown("""
<div class="brand-header">
    <div>
        <h1 class="brand-title">QUERY.SPEAK</h1>
        <div style="font-size: 13px; color: #94a3b8; margin-top: 4px;">Voice-Driven SQL Studio with Bidirectional NLP & Dynamic Viz</div>
    </div>
    <div style="display: flex; gap: 8px;">
        <span class="badge-chip badge-live">● Engine Active</span>
    </div>
</div>
""", unsafe_allow_html=True)

# 8. Query Console
st.markdown("<div class='console-card'>", unsafe_allow_html=True)

mic_col, text_col = st.columns([1, 4])

with mic_col:
    st.markdown("<p style='font-size: 12px; font-weight:700; color:#94a3b8; margin-bottom: 8px;'>VOICE INPUT</p>", unsafe_allow_html=True)
    voice_prompt = speech_to_text(
        language='en',
        start_prompt="🎙️ Record Voice",
        stop_prompt="⏹ Stop",
        key='voice_recorder'
    )

with text_col:
    st.markdown("<p style='font-size: 12px; font-weight:700; color:#94a3b8; margin-bottom: 8px;'>COMMAND PROMPT</p>", unsafe_allow_html=True)
    text_prompt = st.text_input(
        label="Query prompt",
        label_visibility="collapsed",
        value=voice_prompt if voice_prompt else st.session_state.last_query,
        placeholder="e.g., 'Show total price per category' or 'Add product Smart Watch with price 3499 and category Electronics'"
    )

st.markdown("<p style='font-size: 11px; color: #64748b; margin-top: 6px;'>Examples: 'List products ordered by price' · 'Show orders placed after February 2026' · 'Delete product where name is USB-C Dock'</p>", unsafe_allow_html=True)

exec_col1, _ = st.columns([1, 4])
with exec_col1:
    submit_btn = st.button("⚡ Execute Command", use_container_width=True)

st.markdown("</div>", unsafe_allow_html=True)

def to_excel_buffer(dataframe: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        dataframe.to_excel(writer, index=False, sheet_name='QuerySpeak_Data')
    return buffer.getvalue()

# 9. Pipeline Execution
active_prompt = text_prompt.strip()

if submit_btn and active_prompt:
    st.session_state.last_query = active_prompt
    start_time = time.time()

    with st.spinner("Synthesizing intent & generating bidirectional translation..."):
        current_schema = get_dynamic_schema_summary()

        system_instruction = f"""
        You are an expert SQL engineer. Given this SQLite schema:
        {current_schema}

        Translate the user's natural language request into JSON output with exactly two fields:
        1. "sql": The raw executable SQL statement (no explanations, no backticks).
           - Output INSERT, UPDATE, DELETE, or SELECT based on natural intent.
           - For INSERT, supply sensible defaults for missing columns (e.g. price=1000.0, category='General', date='2026-09-30').
           - Never emit DROP, ALTER, TRUNCATE, or CREATE.
        2. "explanation": A concise, natural 1-sentence plain-English summary of what the query accomplishes.

        Respond with ONLY a valid, raw JSON object:
        {{"sql": "...", "explanation": "..."}}
        """

        try:
            chat_completion = None
            last_err = None

            for m in available_models:
                try:
                    chat_completion = client.chat.completions.create(
                        messages=[
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": active_prompt}
                        ],
                        model=m,
                        temperature=0.1,
                        response_format={"type": "json_object"}
                    )
                    if chat_completion and chat_completion.choices:
                        break
                except Exception as err:
                    last_err = err
                    continue

            if not chat_completion:
                raise Exception(f"Query generation failed: {last_err}")

            raw_json = chat_completion.choices[0].message.content.strip()
            parsed_res = json.loads(raw_json)
            raw_sql = parsed_res.get("sql", "").strip()
            explanation = parsed_res.get("explanation", "Query executed successfully.")

            # Safety Guard
            if any(raw_sql.lower().startswith(x) for x in ["drop", "truncate", "alter"]):
                st.error("Operation Denied: Structural schema changes are prohibited.")
                st.stop()

            cols, rows, action_msg = run_query(raw_sql)
            df = pd.DataFrame(rows, columns=cols) if cols else pd.DataFrame()
            elapsed_time = round(time.time() - start_time, 3)

            # Record Audit History
            st.session_state.audit_history.append({
                "prompt": active_prompt,
                "sql": raw_sql,
                "latency": elapsed_time,
                "rows": len(df)
            })

            # Voice Readback
            tts_speech = f"{explanation}. Found {len(df)} records." if not action_msg else action_msg
            trigger_tts(tts_speech)

            # Telemetry Metrics
            t1, t2, t3, t4 = st.columns(4)
            with t1:
                st.metric("Latency", f"{elapsed_time}s")
            with t2:
                st.metric("Records Returned", len(df))
            with t3:
                st.metric("Operation Mode", "SELECT" if raw_sql.lower().startswith("select") else "MUTATION")
            with t4:
                st.metric("Engine Health", "100% OK")

            # Explanation & SQL Output
            st.markdown(f"<div class='explanation-box'><strong>💡 Natural Explanation:</strong> {explanation}</div>", unsafe_allow_html=True)
            st.markdown("##### 💻 Executed SQL")
            st.code(raw_sql, language="sql")

            if not df.empty:
                # Export Actions
                st.markdown("##### 📋 Result Set")
                head_col, export_csv, export_xlsx = st.columns([3, 1, 1])

                with export_csv:
                    st.download_button(
                        label="📄 Export CSV",
                        data=df.to_csv(index=False).encode('utf-8'),
                        file_name="queryspeak_export.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                with export_xlsx:
                    st.download_button(
                        label="📗 Export Excel",
                        data=to_excel_buffer(df),
                        file_name="queryspeak_export.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

                st.dataframe(df, use_container_width=True)

                # Interactive Multi-Type Visualization
                if raw_sql.lower().startswith("select") and len(cols) >= 2 and len(df) > 1:
                    numeric_cols = [c for c in df.select_dtypes(include=['int64', 'float64']).columns if not c.lower().endswith('_id')]
                    text_cols = [c for c in df.select_dtypes(include=['object']).columns if not c.lower().endswith('_id')]

                    if not numeric_cols:
                        numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns.tolist()
                    if not text_cols:
                        text_cols = df.select_dtypes(include=['object']).columns.tolist()

                    if text_cols and numeric_cols:
                        x_field = text_cols[0]
                        y_field = numeric_cols[-1]

                        st.markdown("##### 📊 Dynamic Visualization Studio")
                        
                        chart_type = st.radio(
                            "Select Projection Type:",
                            ["Bar Chart", "Line Chart", "Donut / Pie Chart"],
                            horizontal=True
                        )

                        if chart_type == "Bar Chart":
                            fig = px.bar(
                                df, x=x_field, y=y_field, color=x_field,
                                title=f"{y_field.replace('_', ' ').title()} by {x_field.replace('_', ' ').title()}",
                                template="plotly_dark"
                            )
                        elif chart_type == "Line Chart":
                            fig = px.line(
                                df, x=x_field, y=y_field, markers=True,
                                title=f"{y_field.replace('_', ' ').title()} across {x_field.replace('_', ' ').title()}",
                                template="plotly_dark"
                            )
                        else:
                            fig = px.pie(
                                df, names=x_field, values=y_field, hole=0.45,
                                title=f"Distribution of {y_field.replace('_', ' ').title()} by {x_field.replace('_', ' ').title()}",
                                template="plotly_dark"
                            )

                        fig.update_layout(
                            paper_bgcolor="rgba(15, 23, 42, 0.4)",
                            plot_bgcolor="rgba(0, 0, 0, 0)",
                            margin=dict(l=20, r=20, t=40, b=20),
                            font=dict(family="Plus Jakarta Sans, sans-serif")
                        )
                        st.plotly_chart(fig, use_container_width=True)

            elif action_msg:
                st.success(action_msg)
            else:
                st.info("Query completed. Zero matching records returned.")

        except sqlite3.Error as db_err:
            st.error(f"Database Runtime Exception: {db_err}")
        except Exception as e:
            st.error(f"Engine Exception: {e}")