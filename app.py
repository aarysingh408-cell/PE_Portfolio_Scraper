import streamlit as st
import asyncio
import subprocess
import sys
import requests
import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from scraper import scrape_portfolio, get_suggestions, DATABASE

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
        justify-content: space-between;
    }
    .ask-header-left { display: flex; align-items: center; gap: 16px; }
    .ask-gold-bar { width: 4px; min-height: 46px; background-color: #BB962C; border-radius: 2px; flex-shrink: 0; }
    .ask-header-title { font-size: 20px; font-weight: 600; color: white; margin: 0 0 4px; }
    .ask-header-sub   { font-size: 13px; color: rgba(255,255,255,0.6); margin: 0; }
    .search-badge {
        background-color: #BB962C;
        color: white;
        font-size: 13px;
        font-weight: 600;
        padding: 6px 14px;
        border-radius: 20px;
        white-space: nowrap;
    }
    .stButton > button {
        background-color: #033A49;
        color: white;
        border: none;
        padding: 0.6rem 1.5rem;
        font-size: 15px;
        font-weight: 500;
        border-radius: 8px;
        margin-top: 6px;
        width: 100%;
    }
    .stButton > button:hover { background-color: #044f65; color: white; border: none; }
    .ask-footer { text-align: center; color: #aaa; font-size: 12px; margin-top: 40px; padding-top: 16px; border-top: 1px solid #f0f0f0; }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────
if "search_count" not in st.session_state:
    st.session_state.search_count = 0
if "firm_to_search" not in st.session_state:
    st.session_state.firm_to_search = ""

# ── Header ────────────────────────────────────────────────────
st.markdown(f"""
<div class="ask-header">
    <div class="ask-header-left">
        <div class="ask-gold-bar"></div>
        <div>
            <p class="ask-header-title">Portscope</p>
            <p class="ask-header-sub">Type any investor name — get a full list of their portfolio companies</p>
        </div>
    </div>
    <div class="search-badge">🔍 {st.session_state.search_count} searches</div>
</div>
""", unsafe_allow_html=True)

# ── API key ───────────────────────────────────────────────────
try:
    api_key = st.secrets["GROQ_API_KEY"]
except Exception:
    st.error('Groq API key missing. Go to Streamlit → Manage App → Settings → Secrets and add:\nGROQ_API_KEY = "gsk_your-key-here"')
    st.stop()

# ── Debug panel ───────────────────────────────────────────────
with st.expander("🔧 Debug info"):
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Test Groq API", key="test_groq"):
            try:
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": "Say: Groq is working"}], "max_tokens": 20},
                    timeout=15
                )
                resp.raise_for_status()
                st.success(f"Groq OK: {resp.json()['choices'][0]['message']['content'][:60]}")
            except Exception as e:
                st.error(f"Groq failed: {e}")
    with col2:
        if st.button("Test Browser", key="test_browser"):
            async def test_browser():
                from playwright.async_api import async_playwright
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
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

# ── Search input ──────────────────────────────────────────────
firm_input = st.text_input(
    label="Investor / PE firm name",
    placeholder="Type name — e.g. EQT, KKR, Carlyle, Warburg Pincus...",
    key="firm_input"
)

# ── Suggestions ───────────────────────────────────────────────
if firm_input and len(firm_input) >= 1:
    suggestions = get_suggestions(firm_input)
    if suggestions:
        st.markdown("**Suggestions from database:**")
        cols = st.columns(min(len(suggestions), 4))
        for i, s in enumerate(suggestions[:8]):
            with cols[i % 4]:
                if st.button(s, key=f"s_{s}"):
                    st.session_state.firm_to_search = s
                    st.rerun()
        st.caption("Click a suggestion above, or type full name and click Search.")

# ── Search button ─────────────────────────────────────────────
search_clicked = st.button("🔍 Search Portfolio", key="search_btn")

# Determine what to search
if search_clicked:
    firm = firm_input.strip()
    if not firm:
        st.warning("Please enter a firm name first.")
    else:
        st.session_state.firm_to_search = firm

# Auto-trigger if suggestion was clicked
firm_to_search = st.session_state.firm_to_search

if firm_to_search and (search_clicked or (firm_to_search.lower() != firm_input.strip().lower())):
    st.session_state.search_count += 1
    status = st.empty()
    companies = []

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        companies = loop.run_until_complete(
            scrape_portfolio(firm_to_search, api_key, status)
        )
        loop.close()
    except Exception as e:
        st.error(f"Error: {e}")

    status.empty()

    if companies:
        st.success(f"✅ Found {len(companies)} companies in {firm_to_search}'s portfolio")
        st.markdown("---")

        # ── Build Excel file ──────────────────────────────────
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"{firm_to_search} Portfolio"

        # Header row
        ws['C4'] = firm_to_search.upper()
        ws['C4'].font = Font(bold=True, size=12)

        # Column headers
        ws['C5'] = "SR NO"
        ws['D5'] = "COMPANY"
        ws['C5'].font = Font(bold=True, color="FFFFFF")
        ws['C5'].fill = PatternFill("solid", fgColor="033A49")
        ws['C5'].alignment = Alignment(horizontal="center")
        ws['D5'].font = Font(bold=True, color="FFFFFF")
        ws['D5'].fill = PatternFill("solid", fgColor="033A49")

        # Data rows
        for i, company in enumerate(companies, 1):
            ws[f'C{5+i}'] = i
            ws[f'D{5+i}'] = company
            ws[f'C{5+i}'].alignment = Alignment(horizontal="center")

        # Column widths
        ws.column_dimensions['C'].width = 10
        ws.column_dimensions['D'].width = 45

        # Save to buffer
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        # ── Download buttons ──────────────────────────────────
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="⬇️ Download as Excel",
                data=buf.getvalue(),
                file_name=f"{firm_to_search.replace(' ', '_')}_portfolio.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        with col2:
            # Copy button using clipboard JS
            copy_text = f"SR NO\tCOMPANY\n" + "\n".join([f"{i+1}\t{c}" for i,c in enumerate(companies)])
            st.download_button(
                label="⬇️ Download as CSV",
                data="SR NO,COMPANY\n" + "\n".join([f"{i+1},{c}" for i,c in enumerate(companies)]),
                file_name=f"{firm_to_search.replace(' ', '_')}_portfolio.csv",
                mime="text/csv"
            )

        # ── Table display ─────────────────────────────────────
        st.markdown(f"### {firm_to_search.upper()} — Portfolio Companies")

        # Build HTML table matching the screenshot format
        rows_html = ""
        for i, company in enumerate(companies, 1):
            bg = "#f8f8f8" if i % 2 == 0 else "#ffffff"
            rows_html += f"""
            <tr style="background:{bg}">
                <td style="padding:8px 14px;border:1px solid #ddd;text-align:center;color:#555;width:80px">{i}</td>
                <td style="padding:8px 14px;border:1px solid #ddd;color:#222">{company}</td>
            </tr>"""

        table_html = f"""
        <table style="width:100%;border-collapse:collapse;font-family:Arial,sans-serif;font-size:14px;margin-top:8px">
            <thead>
                <tr style="background:#033A49">
                    <th style="padding:10px 14px;border:1px solid #ddd;color:white;text-align:center">SR NO</th>
                    <th style="padding:10px 14px;border:1px solid #ddd;color:white;text-align:left">COMPANY</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
        """
        st.markdown(table_html, unsafe_allow_html=True)

    else:
        st.error(f"No companies found for '{firm_to_search}'.")
        st.markdown("""
        **Tips:**
        - Type the exact name e.g. **EQT** not **eqt**
        - Or click a suggestion button from the database
        - Open 🔧 Debug info and run both tests to check status
        """)
    
    # Reset after search
    st.session_state.firm_to_search = ""

# ── Footer ────────────────────────────────────────────────────
st.markdown(
    "<div class='ask-footer'>Built by Aaryaman Singh &nbsp;·&nbsp; Data sourced live from firm websites</div>",
    unsafe_allow_html=True
)
