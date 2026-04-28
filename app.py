import streamlit as st
import asyncio
import subprocess
import sys
import requests

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

# ── Search counter ────────────────────────────────────────────
if "search_count" not in st.session_state:
    st.session_state.search_count = 0

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
        if st.button("Test Groq API"):
            try:
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "llama-3.1-8b-instant",
                        "messages": [{"role": "user", "content": "Say: Groq is working"}],
                        "max_tokens": 20
                    },
                    timeout=15
                )
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"]
                st.success(f"Groq OK: {text[:60]}")
            except Exception as e:
                st.error(f"Groq failed: {e}")

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

    st.markdown("---")
    if st.button("Test EQT step by step"):
        eqt_url = DATABASE["EQT"]["url"]
        st.write(f"1. URL: `{eqt_url}`")
        async def fetch_eqt():
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width":1280,"height":900}
                )
                page = await context.new_page()
                await page.goto(eqt_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)
                html = await page.content()
                await context.close()
                await browser.close()
                return html
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            html = loop.run_until_complete(fetch_eqt())
            loop.close()
            st.write(f"2. HTML length: {len(html)} chars")
            st.write(f"3. HTML snippet:")
            # Show snippet from deeper in HTML where content usually lives
            mid = len(html) // 2
            st.code(html[mid:mid+800])
            # Also check if any company-like words appear
            import re, json
            headings = re.findall(r'<h[234][^>]*>([^<]+)</h[234]>', html)
            st.write(f"Headings found in HTML: {headings[:20]}")

            # Try to extract Next.js data
            match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if match:
                st.write("✅ Found __NEXT_DATA__ JSON in page!")
                try:
                    data = json.loads(match.group(1))
                    st.write(f"JSON keys at root: {list(data.keys())[:10]}")
                    # Show a snippet of the JSON
                    st.code(json.dumps(data, indent=2)[:2000])
                except Exception as je:
                    st.error(f"JSON parse error: {je}")
            else:
                st.warning("No __NEXT_DATA__ found — page may need more time to load")
            st.write("4. Sending to Groq...")
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [{"role": "user", "content": f"List company names you find in this HTML, one per line:\n\n{html[:5000]}"}],
                    "max_tokens": 500
                },
                timeout=30
            )
            st.write(f"5. Groq status: {resp.status_code}")
            if resp.status_code == 200:
                text = resp.json()["choices"][0]["message"]["content"]
                st.success(f"Groq response:\n{text[:1000]}")
            else:
                st.error(f"Groq error: {resp.text[:500]}")
        except Exception as e:
            st.error(f"Failed: {e}")

# ── Search input ──────────────────────────────────────────────
firm_input = st.text_input(
    label="Investor / PE firm name",
    placeholder="Start typing — e.g. kkr, eqt, carlyle, warburg...",
)

# ── Autocomplete suggestions ──────────────────────────────────
selected_firm = None

if firm_input and len(firm_input) >= 1:
    suggestions = get_suggestions(firm_input)
    if suggestions:
        st.markdown("**Suggestions from database:**")
        cols = st.columns(min(len(suggestions), 3))
        for i, suggestion in enumerate(suggestions[:6]):
            with cols[i % 3]:
                if st.button(suggestion, key=f"suggest_{suggestion}"):
                    selected_firm = suggestion
        st.caption("Select one above for best results — or click Search to try as typed.")

firm_to_search = selected_firm or firm_input
search_clicked = st.button("Search Portfolio")

# ── Run search ────────────────────────────────────────────────
if search_clicked:
    if not firm_to_search.strip():
        st.warning("Please enter a firm name first.")
    else:
        st.session_state.search_count += 1
        status = st.empty()
        companies = []
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            companies = loop.run_until_complete(
                scrape_portfolio(firm_to_search.strip(), api_key, status)
            )
            loop.close()
        except Exception as e:
            st.error(f"Error: {e}")

        status.empty()

        if companies:
            st.success(f"Found {len(companies)} companies in {firm_to_search}'s portfolio")
            st.markdown("---")
            csv_data = "Company Name\n" + "\n".join(companies)
            st.download_button(
                label="Download as CSV",
                data=csv_data,
                file_name=f"{firm_to_search.replace(' ', '_')}_portfolio.csv",
                mime="text/csv"
            )
            st.markdown(
                f"<div class='company-count'>{len(companies)} companies found for <strong>{firm_to_search}</strong></div>",
                unsafe_allow_html=True
            )
            col1, col2 = st.columns(2)
            for i, company in enumerate(companies):
                if i % 2 == 0:
                    col1.markdown(f"**{i+1}.** {company}")
                else:
                    col2.markdown(f"**{i+1}.** {company}")
        else:
            st.error(f"No companies found for '{firm_to_search}'.")
            st.markdown("""
            **Tips:**
            - Select a suggestion from the database for best results
            - Check the spelling of the firm name
            - Open 🔧 Debug info and run both tests
            """)

# ── Footer ────────────────────────────────────────────────────
st.markdown(
    "<div class='ask-footer'>Built by Aaryaman Singh &nbsp;·&nbsp; Data sourced live from firm websites</div>",
    unsafe_allow_html=True
)

# ── TEMPORARY: inject step by step test into debug expander ──
# This block adds a test button — remove after debugging is done
