import streamlit as st
import asyncio
import subprocess
import sys
import nest_asyncio

# Fix asyncio event loop conflict with Streamlit
nest_asyncio.apply()

from scraper import scrape_portfolio

# Install Chrome browser on startup — runs once
@st.cache_resource
def install_playwright_browser():
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True
    )

install_playwright_browser()

# ── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="Portscope",
    page_icon="🔍",
    layout="centered"
)

# ── Styling — ASK brand colours ───────────────────────────────
st.markdown("""
<style>
    .main { max-width: 740px; margin: auto; }
    .ask-header {
        background-color: #033A49;
        padding: 22px 28px;
        border-radius: 10px;
        margin-bottom: 28px;
        display: flex;
        align-items: center;
        gap: 16px;
    }
    .ask-gold-bar {
        width: 4px;
        min-height: 46px;
        background-color: #BB962C;
        border-radius: 2px;
        flex-shrink: 0;
    }
    .ask-header-title {
        font-size: 20px;
        font-weight: 600;
        color: white;
        margin: 0 0 4px;
    }
    .ask-header-sub {
        font-size: 13px;
        color: rgba(255,255,255,0.6);
        margin: 0;
    }
    .stButton > button {
        width: 100%;
        background-color: #033A49;
        color: white;
        border: none;
        padding: 0.6rem 1.5rem;
        font-size: 15px;
        font-weight: 500;
        border-radius: 8px;
        margin-top: 6px;
    }
    .stButton > button:hover {
        background-color: #044f65;
        color: white;
        border: none;
    }
    .company-count {
        text-align: center;
        color: #58595B;
        font-size: 14px;
        margin: 16px 0 12px;
    }
    .ask-footer {
        text-align: center;
        color: #aaa;
        font-size: 12px;
        margin-top: 40px;
        padding-top: 16px;
        border-top: 1px solid #f0f0f0;
    }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────
st.markdown("""
<div class="ask-header">
    <div class="ask-gold-bar"></div>
    <div>
        <p class="ask-header-title">Portscope</p>
        <p class="ask-header-sub">Type any investor name — get a full list of their portfolio companies</p>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Check Gemini API key ───────────────────────────────────────
try:
    api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    st.error(
        "Gemini API key missing. "
        "Go to Streamlit → Manage App → Settings → Secrets and add:\n\n"
        'GEMINI_API_KEY = "your-key-here"'
    )
    st.stop()

# ── Input ─────────────────────────────────────────────────────
firm_name = st.text_input(
    label="Investor / PE firm name",
    placeholder="e.g. KKR, EQT, General Atlantic, Warburg Pincus...",
)

search_clicked = st.button("Search Portfolio")

# ── Search ────────────────────────────────────────────────────
if search_clicked:

    if not firm_name.strip():
        st.warning("Please enter a firm name first.")

    else:
        # Show step-by-step status so user knows what's happening
        status = st.empty()
        status.info(f"Opening {firm_name}'s portfolio page...")

        try:
            loop = asyncio.get_event_loop()
            companies = loop.run_until_complete(
                scrape_portfolio(firm_name.strip(), api_key)
            )
        except Exception as e:
            companies = []
            st.error(f"Error: {e}")

        status.empty()

        # ── Results ───────────────────────────────────────────
        if companies:
            st.success(f"Found {len(companies)} companies in {firm_name}'s portfolio")
            st.markdown("---")

            # Download button
            csv_content = "Company Name\n" + "\n".join(companies)
            st.download_button(
                label="Download as CSV",
                data=csv_content,
                file_name=f"{firm_name.replace(' ', '_')}_portfolio.csv",
                mime="text/csv"
            )

            st.markdown(
                f"<div class='company-count'>"
                f"{len(companies)} companies found for <strong>{firm_name}</strong>"
                f"</div>",
                unsafe_allow_html=True
            )

            # Two column list
            col1, col2 = st.columns(2)
            for i, company in enumerate(companies):
                if i % 2 == 0:
                    col1.markdown(f"**{i+1}.** {company}")
                else:
                    col2.markdown(f"**{i+1}.** {company}")

        else:
            st.error(f"No companies found for '{firm_name}'.")
            st.markdown("""
            **Tips to try:**
            - Check the spelling — try exactly as the firm's name appears on their website
            - For database firms try short names: "KKR", "EQT", "Actis"
            - Some websites block automated access
            """)

# ── Footer ────────────────────────────────────────────────────
st.markdown(
    "<div class='ask-footer'>"
    "Built by Aaryaman Singh &nbsp;·&nbsp; "
    "Data sourced live from firm websites"
    "</div>",
    unsafe_allow_html=True
)
