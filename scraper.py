# ============================================================
#  PE FIRM PORTFOLIO SCRAPER
#  You type a PE firm name.
#  This finds their website, finds their portfolio page,
#  and returns a list of companies they have invested in.
# ============================================================

import asyncio
from duckduckgo_search import DDGS
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin


# ============================================================
# STEP 1 — Find the firm's official website
# ============================================================

def find_firm_website(firm_name):
    print(f"\n Searching for '{firm_name}' website...")

    # Sites we want to skip — we want the real company site, not directories
    skip_sites = [
        'wikipedia', 'linkedin', 'crunchbase', 'bloomberg', 'forbes',
        'moneycontrol', 'economictimes', 'yourstory', 'tracxn',
        'pitchbook', 'ambitionbox', 'glassdoor', 'indiamart',
        'zaubacorp', 'tofler', 'twitter', 'facebook', 'instagram',
        'youtube', 'reddit', 'quora', 'medium', 'substack'
    ]

    queries = [
        f"{firm_name} private equity official website",
        f"{firm_name} PE fund portfolio India",
        f'"{firm_name}" site',
    ]

    for query in queries:
        try:
            with DDGS() as ddgs:
                results = ddgs.text(query, max_results=8)
                for result in results:
                    url = result.get('href', '')
                    if not url:
                        continue
                    if not any(skip in url.lower() for skip in skip_sites):
                        print(f" Found: {url}")
                        return url
        except Exception as e:
            print(f" Search attempt failed: {e}")
            continue

    print(" Could not find website.")
    return None


# ============================================================
# STEP 2 — Find the portfolio page link on their website
# ============================================================

def find_portfolio_link(homepage_url, all_links):

    # Keywords that PE firms use for their portfolio page
    # Ordered from most to least specific
    priority_keywords = ['portfolio companies', 'our portfolio', 'investee companies']
    secondary_keywords = ['portfolio', 'companies', 'investments', 'investee',
                          'ventures', 'holdings', 'our companies', 'funded']

    best_url = None

    for keyword in priority_keywords + secondary_keywords:
        for link_text, link_url in all_links:
            if not link_url or link_url.startswith('mailto') or link_url.startswith('tel'):
                continue

            text_match = keyword in link_text.lower()
            url_match  = keyword.replace(' ', '-') in link_url.lower() or \
                         keyword.replace(' ', '_') in link_url.lower() or \
                         keyword.replace(' ', '')  in link_url.lower()

            if text_match or url_match:
                # Fix relative URLs
                if link_url.startswith('/'):
                    parsed = urlparse(homepage_url)
                    full_url = f"{parsed.scheme}://{parsed.netloc}{link_url}"
                elif link_url.startswith('http'):
                    full_url = link_url
                else:
                    full_url = urljoin(homepage_url, link_url)

                # Prefer links that are on the same domain
                if urlparse(homepage_url).netloc in full_url:
                    return full_url
                elif best_url is None:
                    best_url = full_url

    return best_url or homepage_url


# ============================================================
# STEP 3 — Open browser, visit site, scroll, extract HTML
# ============================================================

async def scrape_portfolio(firm_name):

    homepage_url = find_firm_website(firm_name)
    if not homepage_url:
        return []

    companies = []

    print(f"\n Opening browser...")

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )

        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800}
        )

        page = await context.new_page()

        # Block images and fonts to load pages faster
        await page.route('**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}',
                         lambda route: route.abort())

        try:
            # ── Visit homepage ──
            print(f" Visiting: {homepage_url}")
            await page.goto(homepage_url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(2000)

            # ── Collect all links ──
            links = await page.eval_on_selector_all(
                'a[href]',
                'els => els.map(el => [el.innerText.trim(), el.href])'
            )

            # ── Navigate to portfolio page ──
            portfolio_url = find_portfolio_link(homepage_url, links)

            if portfolio_url and portfolio_url != homepage_url:
                print(f" Portfolio page: {portfolio_url}")
                await page.goto(portfolio_url, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(2500)
            else:
                print(f" Using homepage")

            # ── Scroll to load lazy content ──
            print(f" Scrolling to load all companies...")
            prev_height = 0
            for _ in range(8):
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(1200)
                curr_height = await page.evaluate('document.body.scrollHeight')
                if curr_height == prev_height:
                    break
                prev_height = curr_height

            # ── Click common "show more" buttons ──
            more_button_texts = [
                'Load More', 'Show More', 'View More', 'See More',
                'More Companies', 'View All', 'See All'
            ]
            for btn_text in more_button_texts:
                for _ in range(5):
                    try:
                        btn = page.locator(f"text={btn_text}").first
                        if await btn.is_visible(timeout=1500):
                            await btn.click()
                            await page.wait_for_timeout(1500)
                        else:
                            break
                    except:
                        break

            # ── Get final HTML ──
            html = await page.content()
            companies = extract_companies_from_html(html, firm_name)

            # ── Fallback: if very few found, try other nav links ──
            if len(companies) < 3:
                print(f" Few results, trying other links...")
                for link_text, link_url in links:
                    kw = ['portfolio', 'companies', 'investment', 'holdings']
                    if any(k in link_text.lower() or k in link_url.lower() for k in kw):
                        if link_url != portfolio_url and link_url.startswith('http'):
                            try:
                                await page.goto(link_url, wait_until='domcontentloaded', timeout=20000)
                                await page.wait_for_timeout(2000)
                                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                                await page.wait_for_timeout(1500)
                                alt_html = await page.content()
                                alt_companies = extract_companies_from_html(alt_html, firm_name)
                                if len(alt_companies) > len(companies):
                                    companies = alt_companies
                                    break
                            except:
                                continue

        except Exception as e:
            print(f" Error: {e}")

        finally:
            await context.close()
            await browser.close()

    print(f" Found {len(companies)} companies")
    return companies


# ============================================================
# STEP 4 — Extract company names from the HTML
# ============================================================

def extract_companies_from_html(html, firm_name):

    soup = BeautifulSoup(html, 'html.parser')

    # Remove nav, footer, header, scripts — all junk
    for tag in soup(['nav', 'footer', 'header', 'script', 'style',
                     'noscript', 'iframe', 'meta']):
        tag.decompose()

    company_names = []

    # ── Method 1: Headings inside card/grid elements ──
    # Most PE sites show portfolio as a grid of cards with h2/h3/h4 headings
    card_selectors = [
        'article', '.card', '.portfolio-item', '.company', '.investment',
        '.grid-item', '.team-item', '.portfolio-company', '[class*="card"]',
        '[class*="portfolio"]', '[class*="company"]', '[class*="invest"]'
    ]
    for selector in card_selectors:
        cards = soup.select(selector)
        if len(cards) >= 3:  # Only trust if we find multiple cards
            for card in cards:
                heading = card.find(['h2', 'h3', 'h4', 'h5', 'strong'])
                if heading:
                    text = heading.get_text(strip=True)
                    if is_valid_company_name(text, firm_name):
                        company_names.append(text)
            if len(company_names) >= 3:
                break

    # ── Method 2: All headings on page ──
    if len(company_names) < 3:
        headings = soup.find_all(['h2', 'h3', 'h4'])
        for h in headings:
            text = h.get_text(strip=True)
            if is_valid_company_name(text, firm_name):
                company_names.append(text)

    # ── Method 3: Image alt text (logo grids) ──
    if len(company_names) < 3:
        for img in soup.find_all('img', alt=True):
            alt = img['alt'].strip()
            if is_valid_company_name(alt, firm_name):
                company_names.append(alt)

    # ── Method 4: Links with short descriptive text ──
    if len(company_names) < 3:
        for a in soup.find_all('a', href=True):
            text = a.get_text(strip=True)
            if is_valid_company_name(text, firm_name):
                company_names.append(text)

    # ── Method 5: aria-label attributes ──
    if len(company_names) < 3:
        for el in soup.find_all(attrs={"aria-label": True}):
            text = el['aria-label'].strip()
            if is_valid_company_name(text, firm_name):
                company_names.append(text)

    # Remove duplicates, preserve order
    seen = set()
    unique = []
    for name in company_names:
        clean = name.strip()
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            unique.append(clean)

    return unique


# ============================================================
# HELPER — Filter out junk, keep real company names
# ============================================================

def is_valid_company_name(text, firm_name):

    if not text or len(text) < 2 or len(text) > 65:
        return False

    text_lower = text.lower().strip()

    # Common navigation / UI junk words to skip
    junk = [
        'home', 'about', 'about us', 'contact', 'contact us', 'team', 'our team',
        'news', 'blog', 'insights', 'press', 'media', 'events', 'resources',
        'careers', 'jobs', 'work with us', 'join us',
        'login', 'sign in', 'sign up', 'register', 'log in',
        'search', 'menu', 'close', 'open', 'back', 'next', 'previous',
        'privacy', 'privacy policy', 'terms', 'terms of use', 'cookie', 'cookies',
        'copyright', 'all rights reserved', 'follow us', 'connect with us',
        'read more', 'learn more', 'view more', 'see more', 'view all',
        'load more', 'show more', 'see all', 'subscribe', 'newsletter',
        'email', 'phone', 'address', 'location', 'directions',
        'linkedin', 'twitter', 'facebook', 'instagram', 'youtube', 'x',
        'strategy', 'approach', 'philosophy', 'mission', 'vision', 'values',
        'people', 'leadership', 'management', 'partners', 'founders',
        'fund', 'funds', 'sector', 'sectors', 'region', 'regions',
        'asset', 'management', 'capital', 'equity', 'venture',
        'portfolio', 'investments', 'companies', 'holdings',
        'overview', 'introduction', 'summary', 'details',
        'get in touch', 'reach us', 'find us',
        firm_name.lower(),
    ]

    if text_lower in junk:
        return False

    if any(text_lower.startswith(j) for j in ['http', 'www.', '@']):
        return False

    if text.isdigit():
        return False

    # Skip if more than 6 words — likely a sentence not a company name
    if len(text.split()) > 6:
        return False

    # Skip if it's mostly numbers and symbols
    alpha_chars = sum(1 for c in text if c.isalpha())
    if alpha_chars < 2:
        return False

    return True


# ============================================================
# MAIN — Command line runner (for testing locally)
# ============================================================

async def main():
    print("\n" + "=" * 55)
    print("  PE FIRM PORTFOLIO SCRAPER")
    print("=" * 55)

    while True:
        firm_name = input("\n Enter PE firm name (or 'quit' to exit): ").strip()
        if firm_name.lower() in ['quit', 'exit', 'q']:
            break
        if not firm_name:
            continue

        companies = await scrape_portfolio(firm_name)

        print("\n" + "=" * 55)
        if companies:
            print(f" {firm_name.upper()} — {len(companies)} companies")
            print("=" * 55)
            for i, c in enumerate(companies, 1):
                print(f"  {i:3}. {c}")
        else:
            print(f" No companies found for '{firm_name}'")
        print("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
