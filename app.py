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
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": "Say: Groq is working"}], "max_tokens": 20},
                    timeout=15
                )
                resp.raise_for_status()
                st.success(f"Groq OK: {resp.json()['choices'][0]['message']['content'][:60]}")
            except Exception as e:
                st.error(f"Groq failed: {e}")

    with col2:
        if st.button("Test Browser"):
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

    st.markdown("---")
    if st.button("Test EQT — visible text"):
        eqt_url = DATABASE["EQT"]["url"]
        st.write(f"1. URL: `{eqt_url}`")
        st.write("2. Opening page and waiting for full render...")

        async def get_eqt_visible():
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox","--disable-dev-shm-usage"]
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 900}
                )
                page = await context.new_page()
                # Wait for full network idle — all JS must finish
                await page.goto(eqt_url, wait_until="networkidle", timeout=60000)
                await page.wait_for_timeout(5000)
                # Scroll to load lazy content
                for _ in range(6):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1500)
                # Extract only visible text — what a human sees on screen
                visible = await page.evaluate("""() => {
                    const results = [];
                    const walker = document.createTreeWalker(
                        document.body,
                        NodeFilter.SHOW_TEXT,
                        null,
                        false
                    );
                    let node;
                    while (node = walker.nextNode()) {
                        const text = node.textContent.trim();
                        const parent = node.parentElement;
                        if (!parent) continue;
                        const tag = parent.tagName.toLowerCase();
                        if (['script','style','noscript'].includes(tag)) continue;
                        const style = window.getComputedStyle(parent);
                        if (style.display === 'none' || style.visibility === 'hidden') continue;
                        if (text.length >= 2 && text.length <= 80) {
                            results.push(text);
                        }
                    }
                    return [...new Set(results)];
                }""")
                await context.close()
                await browser.close()
                return visible

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            visible_texts = loop.run_until_complete(get_eqt_visible())
            loop.close()

            st.write(f"3. Visible text items found: **{len(visible_texts)}**")
            st.write("Sample (first 80 items):")
            st.code("\n".join(visible_texts[:80]))

            st.write("4. Sending to Groq...")
            text_block = "\n".join(visible_texts[:300])
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [{"role": "user", "content": f"These are all the visible text items on EQT's portfolio page. Extract ONLY the portfolio company names. Return one name per line, nothing else:\n\n{text_block}"}],
                    "temperature": 0,
                    "max_tokens": 1024
                },
                timeout=30
            )
            st.write(f"5. Groq status: {resp.status_code}")
            if resp.status_code == 200:
                answer = resp.json()["choices"][0]["message"]["content"]
                st.success(f"Companies found:\n{answer}")
            else:
                st.error(f"Groq error: {resp.text[:300]}")
        except Exception as e:
            st.error(f"Error: {e}")

# ── Search input with session state fix ──────────────────────
if "selected_firm" not in st.session_state:
    st.session_state.selected_firm = ""

firm_input = st.text_input(
    label="Investor / PE firm name",
    placeholder="Start typing — e.g. kkr, eqt, carlyle, warburg...",
    value=st.session_state.selected_firm,
    key="firm_input_box"
)

# Show suggestions based on what user typed
if firm_input and len(firm_input) >= 1:
    suggestions = get_suggestions(firm_input)
    if suggestions:
        st.markdown("**Suggestions from database:**")
        cols = st.columns(min(len(suggestions), 3))
        for i, suggestion in enumerate(suggestions[:6]):
            with cols[i % 3]:
                if st.button(suggestion, key=f"suggest_{suggestion}"):
                    st.session_state.selected_firm = suggestion
                    st.rerun()
        st.caption("Select one above for best results — or click Search to try as typed.")

# Use whatever is in the input box
firm_to_search = firm_input.strip()
search_clicked = st.button("Search Portfolio")

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
            st.markdown("Open 🔧 Debug info → click **Test EQT — visible text** to diagnose.")

st.markdown(
    "<div class='ask-footer'>Built by Aaryaman Singh &nbsp;·&nbsp; Data sourced live from firm websites</div>",
    unsafe_allow_html=True
)
