import asyncio
import re
import json
import requests
from playwright.async_api import async_playwright
from urllib.parse import urlparse, urljoin

# ============================================================
#  GROQ EXTRACTION
# ============================================================

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

def extract_with_groq(text_content, firm_name, api_key):
    """Send visible text to Groq, get company names back."""
    try:
        resp = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [{
                    "role": "user",
                    "content": (
                        f"Below is all the visible text from {firm_name}'s portfolio page.\n"
                        f"Extract ONLY the names of CURRENT/ACTIVE portfolio/investee companies.\n"
                        f"Rules:\n"
                        f"- Return one company name per line\n"
                        f"- No bullets, numbers, or dashes before names\n"
                        f"- Do NOT include companies marked as Realised, Exited, Divested, or Former\n"
                        f"- Do NOT include navigation items, sector labels, regions, years, fund names\n"
                        f"- Do NOT include tech/web tools: Cloudflare, Cookiebot, Google, LinkedIn, Vimeo, YouTube, Facebook, Twitter\n"
                        f"- Do NOT include cookie consent or privacy-related text\n"
                        f"- Do NOT include '{firm_name}' itself\n"
                        f"- If nothing found, reply: NONE\n\n"
                        f"Text:\n{text_content}"
                    )
                }],
                "temperature": 0,
                "max_tokens": 1024
            },
            timeout=60
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()

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
#  DATABASE
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
    "Actis":                {"url": "https://www.act.is/about-us/portfolio/?_portfolio_status=current&_paged=", "pagination": "actis", "total_pages": 6},
}

DATABASE_LOWER = {k.lower(): k for k in DATABASE.keys()}


def get_suggestions(query):
    if not query:
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
#  GET VISIBLE TEXT FROM PAGE
# ============================================================

JS_VISIBLE_TEXT = """() => {
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
        if (['script','style','noscript','meta'].includes(tag)) continue;
        const style = window.getComputedStyle(parent);
        if (style.display === 'none' || style.visibility === 'hidden') continue;
        if (text.length >= 2 && text.length <= 80) {
            results.push(text);
        }
    }
    return [...new Set(results)];
}"""


async def get_visible_text(page, url):
    """Navigate to URL and extract all visible text."""
    try:
        # Use domcontentloaded first, then wait extra time for JS
        await page.goto(url, wait_until='domcontentloaded', timeout=45000)
        await page.wait_for_timeout(6000)

        # Close cookie banners and popups — wait a bit for them to appear
        await page.wait_for_timeout(2000)
        for sel in [
            'button:has-text("Accept all")',
            'button:has-text("Accept All")',
            'button:has-text("Accept cookies")',
            'button:has-text("Accept")',
            'button:has-text("Allow all")',
            'button:has-text("Allow All")',
            'button:has-text("I agree")',
            'button:has-text("Agree")',
            'button:has-text("OK")',
            'button:has-text("Got it")',
            'button:has-text("Close")',
            'button[aria-label="Close"]',
            'button[aria-label="close"]',
            '[class*="accept"]',
            '[class*="cookie"] button',
            '[id*="cookie"] button',
        ]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=600):
                    await btn.click()
                    await page.wait_for_timeout(1000)
                    break
            except: continue
        try:
            await page.keyboard.press('Escape')
            await page.wait_for_timeout(500)
        except: pass

        # Scroll to load lazy content
        for _ in range(6):
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(1500)

        # Extract visible text
        visible = await page.evaluate(JS_VISIBLE_TEXT)
        return visible

    except Exception as e:
        print(f"Page fetch error: {e}")
        return []


# ============================================================
#  MAIN SCRAPER
# ============================================================

async def scrape_portfolio(firm_name, api_key, status_widget=None):

    def update(msg):
        print(msg)
        if status_widget:
            status_widget.info(msg)

    # Try exact match first, then case-insensitive
    db = find_in_database(firm_name)
    # Also try with title case and upper case
    if not db:
        db = find_in_database(firm_name.title())
    if not db:
        db = find_in_database(firm_name.upper())

    if db:
        portfolio_url = db['url']
        pagination    = db.get('pagination', 'single')
        total_pages   = db.get('total_pages', 1)
        update(f"Step 1/3 — Found {firm_name} in database ✓")
    else:
        update(f"Step 1/3 — Searching for {firm_name} online...")
        homepage = find_firm_website(firm_name)
        if not homepage:
            return []
        portfolio_url = None
        pagination    = 'single'
        total_pages   = 1

    all_text_blocks = []
    update("Step 2/3 — Opening portfolio page...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
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

        try:
            # If not in database, find portfolio page first
            if not portfolio_url:
                await page.goto(homepage, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(2000)
                links = await page.eval_on_selector_all(
                    'a[href]',
                    'els => els.map(el => [el.innerText.trim(), el.href])'
                )
                portfolio_url = find_portfolio_page(homepage, links)

            if pagination == 'single':
                visible = await get_visible_text(page, portfolio_url)
                if visible:
                    all_text_blocks.append('\n'.join(visible[:300]))

            elif pagination == 'load_more':
                await page.goto(portfolio_url, wait_until='domcontentloaded', timeout=45000)
                await page.wait_for_timeout(5000)
                # Close popups first
                await page.wait_for_timeout(2000)
                for sel in [
                    'button:has-text("Accept all")', 'button:has-text("Accept All")',
                    'button:has-text("Accept cookies")', 'button:has-text("Accept")',
                    'button:has-text("Allow all")', 'button:has-text("I agree")',
                    'button:has-text("OK")', 'button:has-text("Got it")',
                    '[class*="accept"]', '[class*="cookie"] button',
                ]:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=600):
                            await btn.click()
                            await page.wait_for_timeout(1000)
                            break
                    except: continue

                # Click load more / next page buttons repeatedly
                for _ in range(30):
                    clicked = False
                    for txt in [
                        'Load More', 'Show More', 'View More',
                        'Load more', 'Show more', 'View more',
                        'Next', 'Next page', 'Next Page',
                        'More', 'See more', 'See More',
                    ]:
                        try:
                            btn = page.locator(f"text={txt}").first
                            if await btn.is_visible(timeout=1000):
                                await btn.click()
                                await page.wait_for_timeout(2500)
                                clicked = True
                                print(f"Clicked: {txt}")
                                break
                        except: continue

                    # Also try scrolling to trigger infinite scroll
                    if not clicked:
                        prev_height = await page.evaluate('document.body.scrollHeight')
                        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                        await page.wait_for_timeout(2000)
                        new_height = await page.evaluate('document.body.scrollHeight')
                        if new_height == prev_height:
                            break  # Page stopped growing — we have everything

                visible = await page.evaluate(JS_VISIBLE_TEXT)
                if visible:
                    all_text_blocks.append('\n'.join(visible[:500]))

            elif pagination == 'numbered':
                for pg in range(1, total_pages + 1):
                    update(f"Step 2/3 — Loading page {pg}/{total_pages}...")
                    sep = '&' if '?' in portfolio_url else '?'
                    page_url = f"{portfolio_url}{sep}page={pg}"
                    visible = await get_visible_text(page, page_url)
                    if not visible:
                        break
                    all_text_blocks.append('\n'.join(visible[:300]))

            elif pagination == 'actis':
                # Actis uses ?_portfolio_status=current&_paged=N
                for pg in range(1, total_pages + 1):
                    update(f"Step 2/3 — Loading page {pg}...")
                    page_url = f"{portfolio_url}{pg}"
                    visible = await get_visible_text(page, page_url)
                    if not visible or len(visible) < 5:
                        print(f"Page {pg} empty, stopping")
                        break
                    all_text_blocks.append('\n'.join(visible[:400]))

            elif pagination == 'click_numbered':
                # First load the page
                await page.goto(portfolio_url, wait_until='domcontentloaded', timeout=45000)
                await page.wait_for_timeout(4000)
                # Close popups
                for sel in [
                    'button:has-text("Accept all")', 'button:has-text("Accept All")',
                    'button:has-text("Accept cookies")', 'button:has-text("Accept")',
                    'button:has-text("Allow all")', 'button:has-text("I agree")',
                    '[class*="accept"]', '[class*="cookie"] button',
                ]:
                    try:
                        btn = page.locator(sel).first
                        if await btn.is_visible(timeout=600):
                            await btn.click()
                            await page.wait_for_timeout(1000)
                            break
                    except: continue

                current_page = 1
                while current_page <= total_pages:
                    update(f"Step 2/3 — Reading page {current_page}...")
                    # Scroll to load content
                    for _ in range(3):
                        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                        await page.wait_for_timeout(1000)
                    # Get visible text from current page
                    visible = await page.evaluate(JS_VISIBLE_TEXT)
                    if visible:
                        all_text_blocks.append('\n'.join(visible[:400]))
                    # Try to click next page number
                    next_page = current_page + 1
                    clicked = False
                    # Try clicking the next page number directly
                    for selector in [
                        f'a:has-text("{next_page}")',
                        f'button:has-text("{next_page}")',
                        f'[aria-label="Page {next_page}"]',
                        'a:has-text("›")',
                        'a:has-text(">")',
                        'a:has-text("Next")',
                        '[class*="next"] a',
                        '[class*="next"] button',
                        'li.next a',
                    ]:
                        try:
                            btn = page.locator(selector).first
                            if await btn.is_visible(timeout=1000):
                                await btn.click()
                                await page.wait_for_timeout(3000)
                                clicked = True
                                break
                        except: continue
                    if not clicked:
                        break  # No next page found
                    current_page += 1

        except Exception as e:
            print(f"Browser error: {e}")
        finally:
            await context.close()
            await browser.close()

    if not all_text_blocks:
        print("No text captured")
        return []

    update("Step 3/3 — Extracting company names with Groq AI...")

    all_companies = []
    for text_block in all_text_blocks:
        found = extract_with_groq(text_block, firm_name, api_key)
        all_companies.extend(found)

    # Deduplicate
    seen = set()
    unique = []
    for c in all_companies:
        if c.strip().lower() not in seen:
            seen.add(c.strip().lower())
            unique.append(c.strip())

    return unique
