import asyncio
import re
import requests
from playwright.async_api import async_playwright
from urllib.parse import urlparse, urljoin

# ============================================================
#  GROQ API — completely free, no credit card needed
#  Uses Llama 3 model, 14,400 requests/day free
# ============================================================

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

def extract_with_groq(html, firm_name, api_key):
    # First try Next.js JSON extraction — much faster and more accurate
    nextjs_results = extract_from_nextjs(html, firm_name)
    if len(nextjs_results) >= 3:
        print(f"Found {len(nextjs_results)} companies via Next.js JSON")
        return nextjs_results

    try:
        prompt = f"""You are reading HTML from the portfolio page of an investment firm called "{firm_name}".

Your task: Extract ONLY the names of portfolio companies or investee companies.

Rules:
- Return company names ONLY — one name per line
- Do NOT include sector labels, regions, years, fund names, status words
- Do NOT include navigation text, buttons, descriptions, headers, footers
- Do NOT include the firm name "{firm_name}" itself
- Do NOT add numbers, bullets or dashes before names
- If no company names found, reply with just: NONE

HTML:
{html[:15000]}"""

        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 1024
            },
            timeout=60
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"].strip()

        if not raw or raw.upper() == "NONE":
            return []

        results = []
        for line in raw.split('\n'):
            clean = re.sub(r'^[\d\.\-\*\•\–\—\s]+', '', line).strip()
            if 2 <= len(clean) <= 80:
                results.append(clean)
        return results

    except Exception as e:
        print(f"Groq error: {e}")
        return []



# ============================================================
#  NEXT.JS DATA EXTRACTOR
#  Many modern sites store all data as JSON in __NEXT_DATA__
#  This extracts company names directly from that JSON
# ============================================================

import json

def extract_from_nextjs(html, firm_name):
    """Extract company names from Next.js __NEXT_DATA__ JSON."""
    try:
        import re
        # Find the __NEXT_DATA__ script tag
        match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if not match:
            return []

        data = json.loads(match.group(1))

        # Convert entire JSON to string and search for company-like patterns
        data_str = json.dumps(data)

        # Look for common field names that hold company names
        names = set()
        def search_json(obj, depth=0):
            if depth > 20:
                return
            if isinstance(obj, dict):
                for key, val in obj.items():
                    # Keys that likely contain company names
                    if key.lower() in ['name', 'title', 'company', 'companyname',
                                       'portfolio_company', 'portfoliocompany',
                                       'investee', 'holding']:
                        if isinstance(val, str) and 2 <= len(val) <= 80:
                            names.add(val.strip())
                    else:
                        search_json(val, depth+1)
            elif isinstance(obj, list):
                for item in obj:
                    search_json(item, depth+1)

        search_json(data)

        # Filter out obvious non-company names
        junk = {'current portfolio', 'portfolio', 'investments', 'home', 'about',
                'contact', 'news', 'press', 'careers', 'legal', 'undefined',
                'true', 'false', 'null', firm_name.lower()}
        results = [n for n in names if n.lower() not in junk and len(n.split()) <= 6]
        return sorted(results)

    except Exception as e:
        print(f"Next.js extraction error: {e}")
        return []

# ============================================================
#  DATABASE — 13 firms researched by Aaryaman Singh
# ============================================================

DATABASE = {
    "KKR":                  {"url": "https://www.kkr.com/invest/portfolio",                                                                                                                                                     "pagination": "numbered", "total_pages": 20},
    "Carlyle":              {"url": "https://www.carlyle.com/portfolio?title=&industry=All&field_geography_target_id_verf=196&status=111&field_acquired_value=All&sort_by=title&sort_order=ASC",                                 "pagination": "single"},
    "Carlyle Group":        {"url": "https://www.carlyle.com/portfolio?title=&industry=All&field_geography_target_id_verf=196&status=111&field_acquired_value=All&sort_by=title&sort_order=ASC",                                 "pagination": "single"},
    "Warburg Pincus":       {"url": "https://warburgpincus.com/investments/",                                                                                                                                                   "pagination": "single"},
    "General Atlantic":     {"url": "https://www.generalatlantic.com/investments/?region=India",                                                                                                                                "pagination": "load_more"},
    "TPG":                  {"url": "https://www.tpg.com/portfolio?statuses=Active&geographies=Asia",                                                                                                                           "pagination": "load_more"},
    "TPG Capital":          {"url": "https://www.tpg.com/portfolio?statuses=Active&geographies=Asia",                                                                                                                           "pagination": "load_more"},
    "Advent International": {"url": "https://www.adventinternational.com/investments/?_sft_location_tax=india",                                                                                                                 "pagination": "numbered", "total_pages": 2},
    "Advent":               {"url": "https://www.adventinternational.com/investments/?_sft_location_tax=india",                                                                                                                 "pagination": "numbered", "total_pages": 2},
    "Apax":                 {"url": "https://www.apax.com/partnerships/?status=current",                                                                                                                                        "pagination": "numbered", "total_pages": 8},
    "Apax Partners":        {"url": "https://www.apax.com/partnerships/?status=current",                                                                                                                                        "pagination": "numbered", "total_pages": 8},
    "Bain Capital":         {"url": "https://www.baincapitalprivateequity.com/portfolio",                                                                                                                                       "pagination": "single"},
    "CVC":                  {"url": "https://www.cvc.com/portfolio/our-portfolio/?strategy=all&country=India&industries=all&partner=undefined&cardName=null",                                                                    "pagination": "single"},
    "CVC Capital":          {"url": "https://www.cvc.com/portfolio/our-portfolio/?strategy=all&country=India&industries=all&partner=undefined&cardName=null",                                                                    "pagination": "single"},
    "CVC Capital Partners": {"url": "https://www.cvc.com/portfolio/our-portfolio/?strategy=all&country=India&industries=all&partner=undefined&cardName=null",                                                                    "pagination": "single"},
    "EQT":                  {"url": "https://eqtgroup.com/about/current-portfolio?country=india",                                                                                                                               "pagination": "single"},
    "PAG":                  {"url": "https://www.pag.com/en/private-equity/#portfolio",                                                                                                                                         "pagination": "single"},
    "Actis":                {"url": "https://www.act.is/about-us/portfolio/?_portfolio_status=current",                                                                                                                         "pagination": "numbered", "total_pages": 3},
}

DATABASE_LOWER = {k.lower(): k for k in DATABASE.keys()}


def get_suggestions(query):
    if not query or len(query) < 1:
        return []
    q = query.lower().strip()
    return [DATABASE_LOWER[k] for k in DATABASE_LOWER if q in k]


def find_in_database(firm_name):
    key = firm_name.lower().strip()
    if key in DATABASE_LOWER:
        return DATABASE[DATABASE_LOWER[key]]
    return None


# ============================================================
#  FIND WEBSITE — fallback for unknown firms
# ============================================================

def find_firm_website(firm_name):
    try:
        from duckduckgo_search import DDGS
        skip = ['wikipedia','linkedin','crunchbase','bloomberg','economictimes',
                'moneycontrol','yourstory','tracxn','pitchbook','twitter',
                'facebook','instagram','youtube','inc42','businesstoday','livemint']
        with DDGS() as ddgs:
            results = ddgs.text(f'"{firm_name}" portfolio investments official site', max_results=8)
            for r in results:
                url = r.get('href', '')
                if url and not any(s in url.lower() for s in skip):
                    return url
    except Exception as e:
        print(f"Search error: {e}")
    return None


def find_portfolio_page(homepage_url, links):
    keywords = ['portfolio','companies','investments','investee','ventures','holdings']
    for kw in keywords:
        for text, url in links:
            if not url: continue
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
    for sel in ['button[aria-label="Close"]','button[aria-label="close"]',
                '.modal-close','button:has-text("Close")','button:has-text("Accept")']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=500):
                await btn.click()
                await page.wait_for_timeout(500)
                return
        except: continue
    try:
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(300)
    except: pass


async def scroll_fully(page):
    prev = 0
    for _ in range(8):
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await page.wait_for_timeout(1200)
        curr = await page.evaluate('document.body.scrollHeight')
        if curr == prev: break
        prev = curr


# ============================================================
#  MAIN SCRAPER
# ============================================================

async def scrape_portfolio(firm_name, api_key, status_widget=None):

    def update(msg):
        print(msg)
        if status_widget:
            status_widget.info(msg)

    db = find_in_database(firm_name)

    if db:
        portfolio_url = db['url']
        pagination    = db.get('pagination', 'single')
        total_pages   = db.get('total_pages', 1)
        update(f"Step 1/3 — {firm_name} found in database, opening portfolio page...")
    else:
        update(f"Step 1/3 — Searching for {firm_name} online...")
        homepage = find_firm_website(firm_name)
        if not homepage:
            return []
        portfolio_url = None
        pagination    = 'single'
        total_pages   = 1

    all_html = []
    update("Step 2/3 — Loading page and reading content...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox','--disable-dev-shm-usage']
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 900}
        )
        page = await context.new_page()
        await page.route('**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,mp4,mp3}',
                         lambda route: route.abort())

        try:
            if not portfolio_url:
                await page.goto(homepage, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(2000)
                links = await page.eval_on_selector_all('a[href]','els => els.map(el => [el.innerText.trim(), el.href])')
                portfolio_url = find_portfolio_page(homepage, links)

            if pagination == 'single':
                await page.goto(portfolio_url, wait_until='networkidle', timeout=60000)
                await page.wait_for_timeout(5000)
                await try_close_popups(page)
                # Wait for actual content to appear — not just JS to load
                try:
                    await page.wait_for_selector('h2, h3, h4, article, .card, [class*="card"], [class*="portfolio"], [class*="company"]', timeout=15000)
                except:
                    pass
                await scroll_fully(page)
                # Scroll back up and down again to trigger lazy loading
                await page.evaluate('window.scrollTo(0, 0)')
                await page.wait_for_timeout(1000)
                await scroll_fully(page)
                all_html.append(await page.content())

            elif pagination == 'load_more':
                await page.goto(portfolio_url, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(3000)
                await try_close_popups(page)
                for _ in range(20):
                    clicked = False
                    for txt in ['Load More','Show More','View More','Load more','Show more','More']:
                        try:
                            btn = page.locator(f"text={txt}").first
                            if await btn.is_visible(timeout=1000):
                                await btn.click()
                                await page.wait_for_timeout(2000)
                                clicked = True
                                break
                        except: continue
                    if not clicked: break
                await scroll_fully(page)
                all_html.append(await page.content())

            elif pagination == 'numbered':
                for pg in range(1, total_pages + 1):
                    sep = '&' if '?' in portfolio_url else '?'
                    page_url = f"{portfolio_url}{sep}page={pg}"
                    await page.goto(page_url, wait_until='domcontentloaded', timeout=30000)
                    await page.wait_for_timeout(2500)
                    if pg == 1: await try_close_popups(page)
                    await scroll_fully(page)
                    html = await page.content()
                    if len(html) < 500: break
                    all_html.append(html)

        except Exception as e:
            print(f"Browser error: {e}")
        finally:
            await context.close()
            await browser.close()

    if not all_html:
        return []

    update("Step 3/3 — Extracting company names with Groq AI...")

    all_companies = []
    for html in all_html:
        found = extract_with_groq(html, firm_name, api_key)
        all_companies.extend(found)

    seen = set()
    unique = []
    for c in all_companies:
        if c.strip().lower() not in seen:
            seen.add(c.strip().lower())
            unique.append(c.strip())

    return unique
    
