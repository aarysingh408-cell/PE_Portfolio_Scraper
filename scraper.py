import asyncio
import re
import nest_asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import google.generativeai as genai

# Fix asyncio conflict with Streamlit
nest_asyncio.apply()

# ============================================================
#  DATABASE — 13 firms researched manually by Aaryaman Singh
# ============================================================

DATABASE = {
    "kkr": {
        "url": "https://www.kkr.com/invest/portfolio",
        "pagination": "numbered",
        "total_pages": 20,
    },
    "carlyle": {
        "url": "https://www.carlyle.com/portfolio?title=&industry=All&field_geography_target_id_verf=196&status=111&field_acquired_value=All&sort_by=title&sort_order=ASC",
        "pagination": "single",
    },
    "carlyle group": {
        "url": "https://www.carlyle.com/portfolio?title=&industry=All&field_geography_target_id_verf=196&status=111&field_acquired_value=All&sort_by=title&sort_order=ASC",
        "pagination": "single",
    },
    "warburg pincus": {
        "url": "https://warburgpincus.com/investments/",
        "pagination": "single",
    },
    "general atlantic": {
        "url": "https://www.generalatlantic.com/investments/?region=India",
        "pagination": "load_more",
    },
    "tpg": {
        "url": "https://www.tpg.com/portfolio?statuses=Active&geographies=Asia",
        "pagination": "load_more",
    },
    "tpg capital": {
        "url": "https://www.tpg.com/portfolio?statuses=Active&geographies=Asia",
        "pagination": "load_more",
    },
    "advent international": {
        "url": "https://www.adventinternational.com/investments/?_sft_location_tax=india",
        "pagination": "numbered",
        "total_pages": 2,
    },
    "advent": {
        "url": "https://www.adventinternational.com/investments/?_sft_location_tax=india",
        "pagination": "numbered",
        "total_pages": 2,
    },
    "apax": {
        "url": "https://www.apax.com/partnerships/?status=current",
        "pagination": "numbered",
        "total_pages": 8,
    },
    "apax partners": {
        "url": "https://www.apax.com/partnerships/?status=current",
        "pagination": "numbered",
        "total_pages": 8,
    },
    "bain capital": {
        "url": "https://www.baincapitalprivateequity.com/portfolio",
        "pagination": "single",
    },
    "cvc": {
        "url": "https://www.cvc.com/portfolio/our-portfolio/?strategy=all&country=India&industries=all&partner=undefined&cardName=null",
        "pagination": "single",
    },
    "cvc capital": {
        "url": "https://www.cvc.com/portfolio/our-portfolio/?strategy=all&country=India&industries=all&partner=undefined&cardName=null",
        "pagination": "single",
    },
    "cvc capital partners": {
        "url": "https://www.cvc.com/portfolio/our-portfolio/?strategy=all&country=India&industries=all&partner=undefined&cardName=null",
        "pagination": "single",
    },
    "eqt": {
        "url": "https://eqtgroup.com/about/current-portfolio?country=india",
        "pagination": "single",
    },
    "pag": {
        "url": "https://www.pag.com/en/private-equity/#portfolio",
        "pagination": "single",
    },
    "actis": {
        "url": "https://www.act.is/about-us/portfolio/?_portfolio_status=current",
        "pagination": "numbered",
        "total_pages": 3,
    },
}


# ============================================================
#  GEMINI EXTRACTION — sends HTML, gets company names only
# ============================================================

def extract_with_gemini(html, firm_name, api_key):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        # Trim HTML — 15,000 chars is enough for most pages
        html_trimmed = html[:15000]

        prompt = f"""You are reading HTML from the portfolio page of "{firm_name}".

Extract ONLY the names of portfolio/investee companies.

Rules:
- Return ONLY company names, one name per line
- Do NOT include sector labels, regions, years, statuses, fund names
- Do NOT include navigation items, buttons, descriptions, headers
- Do NOT include "{firm_name}" itself
- Do NOT add numbering, bullets, dashes or any punctuation before names
- If no company names found, return exactly: NONE

HTML:
{html_trimmed}"""

        response = model.generate_content(prompt)
        raw = response.text.strip()

        if not raw or raw.upper() == "NONE":
            return []

        companies = []
        for line in raw.split('\n'):
            # Strip bullets, numbers, dashes from start
            clean = re.sub(r'^[\d\.\-\*\•\–\—\s]+', '', line).strip()
            # Skip very short or very long lines
            if 2 <= len(clean) <= 80:
                companies.append(clean)

        return companies

    except Exception as e:
        print(f"Gemini error: {e}")
        return []


# ============================================================
#  FIND WEBSITE — used only when firm is NOT in database
# ============================================================

def find_firm_website(firm_name):
    try:
        from duckduckgo_search import DDGS
        skip = [
            'wikipedia', 'linkedin', 'crunchbase', 'bloomberg',
            'economictimes', 'moneycontrol', 'yourstory', 'tracxn',
            'pitchbook', 'twitter', 'facebook', 'instagram', 'youtube',
            'inc42', 'businesstoday', 'livemint', 'forbes'
        ]
        with DDGS() as ddgs:
            results = ddgs.text(
                f'"{firm_name}" portfolio investments official site',
                max_results=8
            )
            for r in results:
                url = r.get('href', '')
                if url and not any(s in url.lower() for s in skip):
                    return url
    except Exception as e:
        print(f"Search error: {e}")
    return None


def find_portfolio_page(homepage_url, links):
    keywords = ['portfolio', 'companies', 'investments',
                 'investee', 'ventures', 'holdings']
    for kw in keywords:
        for text, url in links:
            if not url:
                continue
            if kw in text.lower() or kw in url.lower():
                if url.startswith('/'):
                    p = urlparse(homepage_url)
                    return f"{p.scheme}://{p.netloc}{url}"
                elif url.startswith('http'):
                    return url
    return homepage_url


# ============================================================
#  BROWSER HELPERS
# ============================================================

async def try_close_popups(page):
    """Try to close any popup — does NOT navigate."""
    selectors = [
        'button[aria-label="Close"]',
        'button[aria-label="close"]',
        '.modal-close', '.popup-close',
        '[class*="modal"] button',
        'button:has-text("Close")',
        'button:has-text("No thanks")',
        'button:has-text("Accept")',
        'button:has-text("Got it")',
        'button:has-text("Dismiss")',
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=500):
                await btn.click()
                await page.wait_for_timeout(500)
                return
        except:
            continue
    try:
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(300)
    except:
        pass


async def scroll_fully(page):
    """Scroll to the bottom repeatedly until page stops growing."""
    prev = 0
    for _ in range(10):
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await page.wait_for_timeout(1000)
        curr = await page.evaluate('document.body.scrollHeight')
        if curr == prev:
            break
        prev = curr


# ============================================================
#  MAIN SCRAPER
# ============================================================

async def scrape_portfolio(firm_name, api_key):
    """Opens browser, gets HTML, sends to Gemini, returns company names."""

    # Check database
    db = None
    key = firm_name.lower().strip()
    if key in DATABASE:
        db = DATABASE[key]
    else:
        for k in DATABASE:
            if k in key or key in k:
                db = DATABASE[k]
                break

    if db:
        portfolio_url = db['url']
        pagination    = db.get('pagination', 'single')
        total_pages   = db.get('total_pages', 1)
        print(f"Database hit: {firm_name} → {portfolio_url}")
    else:
        print(f"Not in database, searching for {firm_name}...")
        homepage = find_firm_website(firm_name)
        if not homepage:
            return []
        portfolio_url = None
        pagination    = 'single'
        total_pages   = 1

    all_html = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage',
                  '--disable-blink-features=AutomationControlled']
        )
        context = await browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            viewport={'width': 1280, 'height': 900}
        )
        page = await context.new_page()

        # Block heavy resources — faster loading
        await page.route(
            '**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,mp4,mp3}',
            lambda route: route.abort()
        )

        try:
            # If not in database, discover portfolio page first
            if not portfolio_url:
                await page.goto(homepage, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(2000)
                links = await page.eval_on_selector_all(
                    'a[href]',
                    'els => els.map(el => [el.innerText.trim(), el.href])'
                )
                portfolio_url = find_portfolio_page(homepage, links)

            # ── SINGLE PAGE ──
            if pagination == 'single':
                print(f"Loading: {portfolio_url}")
                await page.goto(portfolio_url, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(3000)
                await try_close_popups(page)
                await scroll_fully(page)
                all_html.append(await page.content())

            # ── LOAD MORE ──
            elif pagination == 'load_more':
                print(f"Loading (with load more): {portfolio_url}")
                await page.goto(portfolio_url, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(3000)
                await try_close_popups(page)

                load_texts = [
                    'Load More', 'Show More', 'View More',
                    'See More', 'Load more', 'Show more', 'More'
                ]
                for _ in range(20):
                    clicked = False
                    for txt in load_texts:
                        try:
                            btn = page.locator(f"text={txt}").first
                            if await btn.is_visible(timeout=1000):
                                await btn.click()
                                await page.wait_for_timeout(2000)
                                await scroll_fully(page)
                                print(f"  Clicked: {txt}")
                                clicked = True
                                break
                        except:
                            continue
                    if not clicked:
                        break

                await scroll_fully(page)
                all_html.append(await page.content())

            # ── NUMBERED PAGES ──
            elif pagination == 'numbered':
                for pg in range(1, total_pages + 1):
                    print(f"Page {pg}/{total_pages}")
                    sep = '&' if '?' in portfolio_url else '?'
                    page_url = f"{portfolio_url}{sep}page={pg}"

                    await page.goto(page_url, wait_until='domcontentloaded', timeout=30000)
                    await page.wait_for_timeout(2500)

                    if pg == 1:
                        await try_close_popups(page)

                    await scroll_fully(page)
                    html = await page.content()

                    # Stop if page is empty
                    if len(html) < 500:
                        print(f"  Page {pg} empty, stopping")
                        break

                    all_html.append(html)

        except Exception as e:
            print(f"Browser error: {e}")
        finally:
            await context.close()
            await browser.close()

    if not all_html:
        print("No HTML captured")
        return []

    # ── Send to Gemini ──
    print(f"Sending {len(all_html)} page(s) to Gemini...")
    all_companies = []
    for i, html in enumerate(all_html):
        found = extract_with_gemini(html, firm_name, api_key)
        print(f"  Page {i+1}: {len(found)} companies")
        all_companies.extend(found)

    # Deduplicate
    seen = set()
    unique = []
    for c in all_companies:
        if c.strip().lower() not in seen:
            seen.add(c.strip().lower())
            unique.append(c.strip())

    print(f"Total: {len(unique)} unique companies")
    return unique
