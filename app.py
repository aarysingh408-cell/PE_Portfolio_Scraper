import streamlit as st
import asyncio
import subprocess
import sys
import requests
import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

from scraper import scrape_portfolio, get_suggestions, DATABASE, JS_VISIBLE_TEXT, extract_with_groq, find_in_database

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
    .search-badge { background-color: #BB962C; color: white; font-size: 13px; font-weight: 600; padding: 6px 14px; border-radius: 20px; white-space: nowrap; }
    .stButton > button { background-color: #033A49; color: white; border: none; padding: 0.6rem 1.5rem; font-size: 15px; font-weight: 500; border-radius: 8px; margin-top: 6px; width: 100%; }
    .stButton > button:hover { background-color: #044f65; color: white; border: none; }
    .ask-footer { text-align: center; color: #aaa; font-size: 12px; margin-top: 40px; padding-top: 16px; border-top: 1px solid #f0f0f0; }
</style>
""", unsafe_allow_html=True)

if "search_count" not in st.session_state:
    st.session_state.search_count = 0
if "firm_to_search" not in st.session_state:
    st.session_state.firm_to_search = ""

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

try:
    api_key = st.secrets["GROQ_API_KEY"]
except Exception:
    st.error('Groq API key missing. Go to Streamlit → Manage App → Settings → Secrets and add:\nGROQ_API_KEY = "gsk_your-key-here"')
    st.stop()

# ── DEBUG PANEL ───────────────────────────────────────────────
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
                    browser = await p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--disable-background-networking","--js-flags=--max-old-space-size=512"])
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
    st.markdown("**🔍 Universal Step-by-Step Debugger**")
    debug_firm = st.text_input("Type any firm name to debug:", key="debug_input", placeholder="e.g. KKR, EQT, Actis...")

    if st.button("Run Step-by-Step Debug", key="run_debug") and debug_firm.strip():

        firm = debug_firm.strip()
        st.markdown(f"### Debugging: {firm}")

        # ── STEP 1: Database ──────────────────────────────────
        st.markdown("**Step 1 — Database check**")
        db = find_in_database(firm)
        if db:
            st.success(f"✅ Found in database")
            st.write(f"URL: `{db['url']}`")
            st.write(f"Pagination type: `{db.get('pagination', 'single')}`")
            portfolio_url = db['url']
            pagination    = db.get('pagination', 'single')
        else:
            st.warning(f"⚠️ Not in database — would search online")
            portfolio_url = None
            pagination    = 'single'

        # ── STEP 2: Browser ───────────────────────────────────
        st.markdown("**Step 2 — Opening browser and loading page**")

        async def debug_fetch(url):
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu","--disable-background-networking","--js-flags=--max-old-space-size=512"])
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 900}
                )
                page = await context.new_page()
                # Block heavy resources to prevent crashes
                await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,otf,mp4,mp3}", lambda route: route.abort())
                await page.route("**/{analytics,gtm,hotjar,intercom,hubspot,segment}**", lambda route: route.abort())
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    await page.wait_for_timeout(5000)
                    title = await page.title()

                    # Dismiss cookie banners
                    popup_dismissed = None
                    for sel in ['button:has-text("Accept all")', 'button:has-text("Accept All")',
                                'button:has-text("Accept cookies")', 'button:has-text("Accept")',
                                'button:has-text("Allow all")', 'button:has-text("I agree")',
                                '#CybotCookiebotDialogBodyButtonAccept', '.cc-btn.cc-allow']:
                        try:
                            btn = page.locator(sel).first
                            if await btn.is_visible(timeout=500):
                                await btn.click()
                                await page.wait_for_timeout(1000)
                                popup_dismissed = sel
                                break
                        except: continue

                    # Remove cookie overlays from DOM
                    await page.evaluate("""() => {
                        ['[class*="cookie"]','[class*="consent"]','[class*="gdpr"]',
                         '[class*="overlay"]','#onetrust-banner-sdk','.cookielaw-banner'
                        ].forEach(s => document.querySelectorAll(s).forEach(e => e.remove()));
                    }""")

                    # Scroll
                    for _ in range(6):
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await page.wait_for_timeout(1200)

                    # Get visible text
                    visible = await page.evaluate(JS_VISIBLE_TEXT)

                    return {
                        "title": title,
                        "popup": popup_dismissed,
                        "visible": visible,
                        "count": len(visible)
                    }
                except Exception as e:
                    return {"error": str(e)}
                finally:
                    await context.close()
                    await browser.close()

        if portfolio_url:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(debug_fetch(portfolio_url))
                loop.close()

                if "error" in result:
                    st.error(f"❌ Browser error: {result['error']}")
                else:
                    st.success(f"✅ Page loaded: **{result['title']}**")
                    if result["popup"]:
                        st.write(f"Cookie banner dismissed: `{result['popup']}`")
                    st.write(f"Visible text items captured: **{result['count']}**")

                    st.markdown("**First 60 visible text items:**")
                    st.code("\n".join(result["visible"][:60]))

                    # ── STEP 3: Groq ──────────────────────────
                    st.markdown("**Step 3 — Sending to Groq**")
                    text_block = "\n".join(result["visible"][:300])
                    companies = extract_with_groq(text_block, firm, api_key)

                    if companies:
                        st.success(f"✅ Groq found **{len(companies)}** companies:")
                        for c in companies:
                            st.write(f"  • {c}")
                    else:
                        st.error("❌ Groq returned nothing")
                        st.markdown("**Raw text sent to Groq (first 1000 chars):**")
                        st.code(text_block[:1000])

            except Exception as e:
                st.error(f"Debug failed: {e}")
        else:
            st.warning("No URL in database — cannot debug without URL")

# ── SEARCH INPUT ──────────────────────────────────────────────
firm_input = st.text_input(
    label="Investor / PE firm name",
    placeholder="Type name — e.g. EQT, KKR, Carlyle, Warburg Pincus...",
    key="firm_input"
)

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

search_clicked = st.button("🔍 Search Portfolio", key="search_btn")

if search_clicked:
    firm = firm_input.strip()
    if not firm:
        st.warning("Please enter a firm name first.")
    else:
        st.session_state.firm_to_search = firm

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

    # Check if site blocks bots
    if len(companies) == 1 and companies[0].startswith("BOT_BLOCKED:"):
        blocked_url = companies[0].replace("BOT_BLOCKED:", "")
        st.warning(f"⚠️ {firm_to_search}'s website blocks automated access.")
        st.markdown(f"""
        This firm's website uses bot protection (Cloudflare) that prevents automated scraping.

        **Visit their portfolio page directly:**
        👉 [{blocked_url}]({blocked_url})
        """)
        companies = []

    if companies:
        st.success(f"✅ Found {len(companies)} companies in {firm_to_search}'s portfolio")
        st.markdown("---")

        # Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"{firm_to_search} Portfolio"
        ws['C4'] = firm_to_search.upper()
        ws['C4'].font = Font(bold=True, size=12)
        ws['C5'] = "SR NO"
        ws['D5'] = "COMPANY"
        ws['C5'].font = Font(bold=True, color="FFFFFF")
        ws['C5'].fill = PatternFill("solid", fgColor="033A49")
        ws['C5'].alignment = Alignment(horizontal="center")
        ws['D5'].font = Font(bold=True, color="FFFFFF")
        ws['D5'].fill = PatternFill("solid", fgColor="033A49")
        for i, company in enumerate(companies, 1):
            ws[f'C{5+i}'] = i
            ws[f'D{5+i}'] = company
            ws[f'C{5+i}'].alignment = Alignment(horizontal="center")
        ws.column_dimensions['C'].width = 10
        ws.column_dimensions['D'].width = 45
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="⬇️ Download as Excel",
                data=buf.getvalue(),
                file_name=f"{firm_to_search.replace(' ', '_')}_portfolio.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        with col2:
            st.download_button(
                label="⬇️ Download as CSV",
                data="SR NO,COMPANY\n" + "\n".join([f"{i+1},{c}" for i,c in enumerate(companies)]),
                file_name=f"{firm_to_search.replace(' ', '_')}_portfolio.csv",
                mime="text/csv"
            )

        # Table
        st.markdown(f"### {firm_to_search.upper()} — Portfolio Companies")
        rows_html = ""
        for i, company in enumerate(companies, 1):
            bg = "#f8f8f8" if i % 2 == 0 else "#ffffff"
            rows_html += f'<tr style="background:{bg}"><td style="padding:8px 14px;border:1px solid #ddd;text-align:center;color:#555;width:80px">{i}</td><td style="padding:8px 14px;border:1px solid #ddd;color:#222">{company}</td></tr>'

        st.markdown(f"""
        <table style="width:100%;border-collapse:collapse;font-family:Arial,sans-serif;font-size:14px;margin-top:8px">
            <thead><tr style="background:#033A49">
                <th style="padding:10px 14px;border:1px solid #ddd;color:white;text-align:center">SR NO</th>
                <th style="padding:10px 14px;border:1px solid #ddd;color:white;text-align:left">COMPANY</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
        </table>""", unsafe_allow_html=True)

    else:
        st.error(f"No companies found for '{firm_to_search}'.")
        st.markdown("Open 🔧 Debug info above → type the firm name → click **Run Step-by-Step Debug**")

    st.session_state.firm_to_search = ""

st.markdown(
    "<div class='ask-footer'>Built by Aaryaman Singh &nbsp;·&nbsp; Data sourced live from firm websites</div>",
    unsafe_allow_html=True
)
