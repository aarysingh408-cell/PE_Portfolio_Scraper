import streamlit as st
import asyncio
import subprocess
import sys
import requests

from scraper import scrape_portfolio

@st.cache_resource
def install_playwright_browser():
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True, text=True
    )
    return result.returncode, result.stdout, result.stderr

code, out, err = install_playwright_browser()

st.set_page_config(page_title="Portscope", page_icon="🔍", layout="centered")

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
    .ask-gold-bar { width: 4px; min-height: 46px; background-color: #BB962C; border-radius: 2px; flex-shrink: 0; }
    .ask-header-title { font-size: 20px; font-weight: 600; color: white; margin: 0 0 4px; }
    .ask-header-sub   { font-size: 13px; color: rgba(255,255,255,0.6); margin: 0; }
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
    .stButton > button:hover { background-color: #044f65; color: white; border: none; }
    .company-count { text-align: center; color: #58595B; font-size: 14px; margin: 16px 0 12px; }
    .ask-footer { text-align: center; color: #aaa; font-size: 12px; margin-top: 40px; padding-top: 16px; border-top: 1px solid #f0f0f0; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="ask-header">
    <div class="ask-gold-bar"></div>
    <div>
        <p class="ask-header-title">Portscope</p>
        <p class="ask-header-sub">Type any investor name — get a full list of their portfolio companies</p>
    </div>
</div>
""", unsafe_allow_html=True)

try:
    api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    st.error('Gemini API key missing. Go to Streamlit → Manage App → Settings → Secrets and add:\nGEMINI_API_KEY = "your-key-here"')
    st.stop()

# ── Debug panel ───────────────────────────────────────────────
with st.expander("🔧 Debug info"):
    st.write(f"Playwright install code: {code}")
    if err: st.write(f"Playwright errors: {err[:300]}")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Test Gemini API"):
            try:
                # Direct HTTP call — no library, no version issues
                resp = requests.post(
                    f"https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={api_key}",
                    json={"contents": [{"parts": [{"text": "Say: working"}]}]},
                    timeout=15
                )
                resp.raise_for_status()
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                st.success(f"Gemini OK: {text[:60]}")
            except Exception as e:
                st.error(f"Gemini failed: {e}")

    with col2:
        if st.button("Test Browser"):
            async def test_browser():
                from playwright.async_api import async_playwright
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True, args=['--no-sandbox','--disable-dev-shm-usage'])
                    page = await browser.new_page()
                    await page.goto("https://example.com", timeout=15000)
                    title = await page.title()
                    await browser.close()
                    return title
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                title = loop.run_until_complete(test_browser())
                loop.close()
                st.success(f"Browser OK: {title}")
            except Exception as e:
                st.error(f"Browser failed: {e}")

# ── Input ─────────────────────────────────────────────────────
firm_name = st.text_input(
    label="Investor / PE firm name",
    placeholder="e.g. EQT, KKR, General Atlantic, Warburg Pincus...",
)

search_clicked = st.button("Search Portfolio")

if search_clicked:
    if not firm_name.strip():
        st.warning("Please enter a firm name first.")
    else:
        status = st.empty()
        companies = []
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            companies = loop.run_until_complete(
                scrape_portfolio(firm_name.strip(), api_key, status)
            )
            loop.close()
        except Exception as e:
            st.error(f"Error: {e}")

        status.empty()

        if companies:
            st.success(f"Found {len(companies)} companies in {firm_name}'s portfolio")
            st.markdown("---")
            csv_data = "Company Name\n" + "\n".join(companies)
            st.download_button(
                label="Download as CSV",
                data=csv_data,
                file_name=f"{firm_name.replace(' ', '_')}_portfolio.csv",
                mime="text/csv"
            )
            st.markdown(
                f"<div class='company-count'>{len(companies)} companies found for <strong>{firm_name}</strong></div>",
                unsafe_allow_html=True
            )
            col1, col2 = st.columns(2)
            for i, company in enumerate(companies):
                if i % 2 == 0:
                    col1.markdown(f"**{i+1}.** {company}")
                else:
                    col2.markdown(f"**{i+1}.** {company}")
        else:
            st.error(f"No companies found for '{firm_name}'.")
            st.markdown("Open the 🔧 Debug info panel above and click both test buttons to diagnose.")

st.markdown(
    "<div class='ask-footer'>Built by Aaryaman Singh &nbsp;·&nbsp; Data sourced live from firm websites</div>",
    unsafe_allow_html=True
)
