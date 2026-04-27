import asyncio
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import google.generativeai as genai

# ============================================================
#  DATABASE — 13 firms researched manually by Aaryaman Singh
#  Exact URLs, layout types, pagination — no guessing needed
# ============================================================

DATABASE = {
    "kkr": {
        "url": "https://www.kkr.com/invest/portfolio",
        "layout": "table",
        "pagination": "numbered",
        "total_pages": 20,
    },
    "carlyle": {
        "url": "https://www.carlyle.com/portfolio?title=&industry=All&field_geography_target_id_verf=196&status=111&field_acquired_value=All&sort_by=title&sort_order=ASC",
        "layout": "card_grid",
        "pagination": "single",
    },
    "carlyle group": {
        "url": "https://www.carlyle.com/portfolio?title=&industry=All&field_geography_target_id_verf=196&status=111&field_acquired_value=All&sort_by=title&sort_order=ASC",
        "layout": "card_grid",
        "pagination": "single",
    },
    "warburg pincus": {
        "url": "https://warburgpincus.com/investments/",
        "layout": "logo_grid",
        "pagination": "single",
    },
    "general atlantic": {
        "url": "https://www.generalatlantic.com/investments/?region=India",
        "layout": "table",
        "pagination": "load_more",
    },
    "tpg": {
        "url": "https://www.tpg.com/portfolio?statuses=Active&geographies=Asia",
        "layout": "logo_grid",
        "pagination": "load_more",
    },
    "tpg capital": {
        "url": "https://www.tpg.com/portfolio?statuses=Active&geographies=Asia",
        "layout": "logo_grid",
        "pagination": "load_more",
    },
    "advent international": {
        "url": "https://www.adventinternational.com/investments/?_sft_location_tax=india#",
        "layout": "table",
        "pagination": "numbered",
        "total_pages": 2,
    },
    "advent": {
        "url": "https://www.adventinternational.com/investments/?_sft_location_tax=india#",
        "layout": "table",
        "pagination": "numbered",
        "total_pages": 2,
    },
    "apax": {
        "url": "https://www.apax.com/partnerships/?status=current",
        "layout": "logo_grid",
        "pagination": "numbered",
        "total_pages": 8,
    },
    "apax partners": {
        "url": "https://www.apax.com/partnerships/?status=current",
        "layout": "logo_grid",
        "pagination": "numbered",
        "total_pages": 8,
    },
    "bain capital": {
        "url": "https://www.baincapitalprivateequity.com/portfolio",
        "layout": "logo_grid",
        "pagination": "single",
    },
    "cvc": {
        "url": "https://www.cvc.com/portfolio/our-portfolio/?strategy=all&country=India&industries=all&partner=undefined&cardName=null",
        "layout": "card_grid",
        "pagination": "single",
    },
    "cvc capital": {
        "url": "https://www.cvc.com/portfolio/our-portfolio/?strategy=all&country=India&industries=all&partner=undefined&cardName=null",
        "layout": "card_grid",
        "pagination": "single",
    },
    "cvc capital partners": {
        "url": "https://www.cvc.com/portfolio/our-portfolio/?strategy=all&country=India&industries=all&partner=undefined&cardName=null",
        "layout": "card_grid",
        "pagination": "single",
    },
    "eqt": {
        "url": "https://eqtgroup.com/about/current-portfolio?country=india",
        "layout": "table",
        "pagination": "single",
    },
    "pag": {
        "url": "https://www.pag.com/en/private-equity/#portfolio",
        "layout": "logo_grid",
        "pagination": "single",
    },
    "actis": {
        "url": "https://www.act.is/about-us/portfolio/?_portfolio_status=current",
        "layout": "card_grid",
        "pagination": "numbered",
        "total_pages": 3,
    },
}


# ============================================================
#  GEMINI EXTRACTION
#  Sends raw HTML to Google Gemini — returns company names only
# ============================================================

def extract_with_gemini(html, firm_name, api_key):
    """Pass HTML to Gemini Flash — returns only company names, nothing else."""
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        # Trim HTML to avoid token limits — 15,000 chars is plenty
        html_trimmed = html[:15000]

        prompt = f"""
You are reading the HTML source code of the portfolio/investments page of a firm called "{firm_name}".

Your job: extract ONLY the names of portfolio companies or investee companies from this HTML.

Rules:
- Return ONLY company names, one per line
- Do NOT include sector labels, regions, fund names, years, statuses, descriptions
- Do NOT include navigation items, buttons, headers, footers
- Do NOT include the firm's own name "{firm_name}"
- Do NOT include any explanation or commentary
- If you cannot find any company names, return the single word: NONE

HTML:
{html_trimmed}
"""

        response = model.generate_content(prompt)
        raw = response.text.strip()

        if raw == "NONE" or not raw:
            return []

        # Split by newlines, clean each line
        lines = raw.split('\n')
        companies = []
        for line in lines:
            # Remove bullet points, numbers, dashes
            clean = re.sub(r'^[\d\.\-\*\•\–\—\s]+', '', line).strip()
            if clean and len(clean) > 1 and len(clean) < 80:
                companies.append(clean)

        return companies

    except Exception as e:
        print(f" Gemini error: {e}")
        return []


# ============================================================
#  STEP 1 — Find website for unknown firms (fallback only)
# ============================================================

def find_firm_website(firm_name):
    """Used only when firm is NOT in database."""
    try:
        from duckduckgo_search import DDGS
        print(f" Searching online for '{firm_name}'...")

        skip_sites = [
            'wikipedia', 'linkedin', 'crunchbase', 'bloomberg', 'forbes',
            'moneycontrol', 'economictimes', 'yourstory', 'tracxn',
            'pitchbook', 'ambitionbox', 'glassdoor', 'indiamart',
            'twitter', 'facebook', 'instagram', 'youtube', 'reddit',
            'businessinsider', 'livemint', 'inc42', 'businesstoday'
        ]

        with DDGS() as ddgs:
            results = ddgs.text(
                f'"{firm_name}" portfolio investments official site',
                max_results=8
            )
            for result in results:
                url = result.get('href', '')
                if url and not any(s in url.lower() for s in skip_sites):
                    print(f" Found: {url}")
                    return url
    except Exception as e:
        print(f" Search error: {e}")
    return None


def find_portfolio_link(homepage_url, all_links):
    """Scan links on homepage to find portfolio page."""
    keywords = ['portfolio', 'companies', 'investments', 'investee',
                'ventures', 'holdings', 'our companies']
    for keyword in keywords:
        for link_text, link_url in all_links:
            if not link_url:
                continue
            if keyword in link_text.lower() or keyword in link_url.lower():
                if link_url.startswith('/'):
                    parsed = urlparse(homepage_url)
                    return f"{parsed.scheme}://{parsed.netloc}{link_url}"
                elif link_url.startswith('http'):
                    return link_url
    return homepage_url


# ============================================================
#  STEP 2 — Main scraper function
# ============================================================

async def scrape_portfolio(firm_name, api_key):
    """Main entry point. Returns list of company names."""

    # Check database first
    db_entry = None
    key = firm_name.lower().strip()
    if key in DATABASE:
        db_entry = DATABASE[key]
    else:
        for db_key in DATABASE:
            if db_key in key or key in db_key:
                db_entry = DATABASE[db_key]
                break

    if db_entry:
        print(f"\n '{firm_name}' found in database")
        portfolio_url = db_entry['url']
        pagination    = db_entry['pagination']
        total_pages   = db_entry.get('total_pages', 1)
    else:
        print(f"\n '{firm_name}' not in database — searching...")
        homepage_url = find_firm_website(firm_name)
        if not homepage_url:
            return []
        portfolio_url = None
        pagination    = "auto"
        total_pages   = 1

    companies = []

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
            viewport={'width': 1280, 'height': 800}
        )
        page = await context.new_page()

        # Block images and fonts — faster loading
        await page.route(
            '**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}',
            lambda route: route.abort()
        )

        try:
            # If not in database, find portfolio page first
            if not portfolio_url:
                await page.goto(homepage_url, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(2000)
                links = await page.eval_on_selector_all(
                    'a[href]',
                    'els => els.map(el => [el.innerText.trim(), el.href])'
                )
                portfolio_url = find_portfolio_link(homepage_url, links)

            # Scrape based on pagination type
            all_html_chunks = []

            if pagination == "numbered" and total_pages > 1:
                all_html_chunks = await fetch_paginated(page, portfolio_url, total_pages)
            elif pagination == "load_more":
                html = await fetch_load_more(page, portfolio_url)
                all_html_chunks = [html]
            else:
                html = await fetch_single(page, portfolio_url)
                all_html_chunks = [html]

            # Send each chunk to Gemini and collect results
            print(f" Sending to Gemini for extraction...")
            for i, html_chunk in enumerate(all_html_chunks):
                if not html_chunk:
                    continue
                chunk_companies = extract_with_gemini(html_chunk, firm_name, api_key)
                companies.extend(chunk_companies)
                if len(all_html_chunks) > 1:
                    print(f"   Page {i+1}: {len(chunk_companies)} companies")

        except Exception as e:
            print(f" Error: {e}")

        finally:
            await context.close()
            await browser.close()

    # Final deduplication
    seen = set()
    unique = []
    for c in companies:
        if c.lower() not in seen:
            seen.add(c.lower())
            unique.append(c)

    print(f" Total: {len(unique)} companies found")
    return unique


# ============================================================
#  PAGE FETCHERS
# ============================================================

async def close_popups(page):
    """Close any modal/popup that appears."""
    selectors = [
        'button[aria-label="Close"]', 'button[aria-label="close"]',
        '.close', '.modal-close', '.popup-close',
        '[class*="close"]', '[class*="dismiss"]',
        'button:has-text("Close")', 'button:has-text("No thanks")',
        'button:has-text("Accept")', 'button:has-text("Got it")',
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=800):
                await btn.click()
                await page.wait_for_timeout(600)
                break
        except:
            continue
    try:
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(400)
    except:
        pass


async def scroll_to_bottom(page):
    """Scroll until page stops growing."""
    prev_height = 0
    for _ in range(10):
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await page.wait_for_timeout(1000)
        curr_height = await page.evaluate('document.body.scrollHeight')
        if curr_height == prev_height:
            break
        prev_height = curr_height


async def fetch_single(page, url):
    """Fetch one page, scroll, return HTML."""
    print(f" Opening: {url}")
    await page.goto(url, wait_until='domcontentloaded', timeout=30000)
    await page.wait_for_timeout(2500)
    await close_popups(page)
    await scroll_to_bottom(page)
    return await page.content()


async def fetch_load_more(page, url):
    """Fetch page, click all Load More buttons, return final HTML."""
    print(f" Opening (load more): {url}")
    await page.goto(url, wait_until='domcontentloaded', timeout=30000)
    await page.wait_for_timeout(2500)
    await close_popups(page)

    load_more_texts = [
        'Load More', 'Show More', 'View More', 'See More',
        'More', 'Load more', 'Show more', '+'
    ]
    clicks = 0
    while clicks < 25:
        clicked = False
        for btn_text in load_more_texts:
            try:
                btn = page.locator(f"text={btn_text}").first
                if await btn.is_visible(timeout=1200):
                    await btn.click()
                    await page.wait_for_timeout(2000)
                    await scroll_to_bottom(page)
                    clicks += 1
                    clicked = True
                    print(f"   Clicked load more ({clicks})")
                    break
            except:
                continue
        if not clicked:
            break

    await scroll_to_bottom(page)
    return await page.content()


async def fetch_paginated(page, base_url, total_pages):
    """Fetch all numbered pages, return list of HTML strings."""
    html_chunks = []
    print(f" Scraping {total_pages} pages...")

    for page_num in range(1, total_pages + 1):
        print(f"   Page {page_num}/{total_pages}...")

        # Build page URL
        if '?' in base_url:
            page_url = f"{base_url}&page={page_num}"
        else:
            page_url = f"{base_url}?page={page_num}"

        try:
            await page.goto(page_url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(2000)

            if page_num == 1:
                await close_popups(page)

            await scroll_to_bottom(page)
            html = await page.content()

            # If page looks empty stop early
            if len(html) < 1000:
                print(f"   Page {page_num} appears empty, stopping")
                break

            html_chunks.append(html)

        except Exception as e:
            print(f"   Error on page {page_num}: {e}")
            continue

    return html_chunks
