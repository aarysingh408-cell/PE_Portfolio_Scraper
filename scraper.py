# ============================================================
#  PE FIRM PORTFOLIO SCRAPER
#  What this does: You type a PE firm name.
#  It finds their website, finds their portfolio page,
#  and gives you a list of companies they have invested in.
# ============================================================

# These are "libraries" — think of them as pre-built tools
# someone else wrote that we are borrowing.
# Like buying a drill instead of building one from scratch.

import asyncio                                      # Lets the code wait without freezing
from duckduckgo_search import DDGS                  # Free search engine, no account needed
from playwright.async_api import async_playwright   # Controls a real web browser invisibly
from bs4 import BeautifulSoup                       # Reads and understands HTML (webpage code)
from urllib.parse import urlparse                   # Helps us work with URLs


# ============================================================
# STEP 1 — Find the firm's official website
# ============================================================
# When you type "Sequoia Capital", this searches the web
# and returns their actual URL — just like Googling it.

def find_firm_website(firm_name):
    print(f"\n Searching for '{firm_name}' website...")

    with DDGS() as ddgs:
        results = ddgs.text(f"{firm_name} private equity official website India", max_results=5)

        for result in results:
            url = result['href']

            # Skip Wikipedia, LinkedIn, news sites — we want the REAL company website
            skip_sites = [
                'wikipedia', 'linkedin', 'crunchbase', 'bloomberg',
                'forbes', 'moneycontrol', 'economictimes', 'yourstory',
                'tracxn', 'pitchbook', 'ambitionbox'
            ]

            if not any(skip in url for skip in skip_sites):
                print(f"Found website: {url}")
                return url

    print("Could not find website automatically.")
    return None


# ============================================================
# STEP 2 — Find the Portfolio page on their website
# ============================================================
# Every PE firm has a page listing their portfolio companies.
# It might be called "Portfolio", "Our Companies", "Investments"
# This function finds that page by scanning all the links
# on the homepage.

def find_portfolio_link(homepage_url, all_links_on_page):

    keywords = [
        'portfolio', 'companies', 'investments', 'investee',
        'our companies', 'portfolio companies', 'ventures', 'holdings'
    ]

    for link_text, link_url in all_links_on_page:
        link_text_lower = link_text.lower()
        link_url_lower  = link_url.lower()

        for keyword in keywords:
            if keyword in link_text_lower or keyword in link_url_lower:

                # Some links are written as "/portfolio" instead of full URL.
                # We fix that by adding the website domain in front.
                if link_url.startswith('/'):
                    parsed = urlparse(homepage_url)
                    return f"{parsed.scheme}://{parsed.netloc}{link_url}"
                elif link_url.startswith('http'):
                    return link_url

    # If no portfolio link found, stay on the homepage
    return homepage_url


# ============================================================
# STEP 3 — Open browser, visit site, extract company names
# ============================================================
# This opens a real Chrome browser (invisibly),
# goes to the firm's website, scrolls down to load all
# the company cards, then reads the page.

async def scrape_portfolio(firm_name):

    homepage_url = find_firm_website(firm_name)
    if not homepage_url:
        return []

    companies = []

    print(f"\n Opening invisible browser...")

    async with async_playwright() as browser_engine:

        # Launch Chrome without showing a window (headless = invisible)
        browser = await browser_engine.chromium.launch(headless=True)
        page    = await browser.new_page()

        # Tell the website we are a normal human, not a robot
        await page.set_extra_http_headers({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36'
        })

        try:
            # Visit the homepage
            await page.goto(homepage_url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(2000)

            # Collect every clickable link on the homepage
            links_on_page = await page.eval_on_selector_all(
                'a[href]',
                'els => els.map(el => [el.innerText.trim(), el.href])'
            )

            # Find the portfolio page URL
            portfolio_url = find_portfolio_link(homepage_url, links_on_page)

            if portfolio_url != homepage_url:
                print(f" Found portfolio page: {portfolio_url}")
                await page.goto(portfolio_url, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(2000)
            else:
                print(f" Using homepage as portfolio page")

            # Scroll down the page multiple times.
            # Many websites only show company cards after you scroll —
            # this makes sure we load all of them.
            print(f" Scrolling to load all companies...")
            for _ in range(6):
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(1000)

            # Click "Load More" button if one exists
            # Some sites hide companies behind a button
            for _ in range(10):
                try:
                    load_more = page.locator("text=Load More").first
                    if await load_more.is_visible(timeout=2000):
                        await load_more.click()
                        await page.wait_for_timeout(1500)
                        print("   Clicked 'Load More'...")
                    else:
                        break
                except:
                    break

            # Grab the full HTML of the page
            html = await page.content()

            # Extract company names from that HTML
            companies = extract_companies_from_html(html, firm_name)

        except Exception as error:
            print(f" Error while scraping: {error}")

        finally:
            await browser.close()

    return companies


# ============================================================
# STEP 4 — Read the HTML and pull out company names
# ============================================================
# HTML is the raw code of a webpage.
# BeautifulSoup helps us read it like a human would —
# finding headings, links, and images.

def extract_companies_from_html(html, firm_name):

    soup = BeautifulSoup(html, 'html.parser')

    # Remove navigation, footers, headers — they contain junk text
    for tag in soup(['nav', 'footer', 'header', 'script', 'style']):
        tag.decompose()

    company_names = []

    # Method 1: Find repeated headings (h2, h3, h4)
    # PE firms usually show each company name as a heading inside a card
    headings = soup.find_all(['h2', 'h3', 'h4', 'h5'])
    for heading in headings:
        text = heading.get_text(strip=True)
        if is_valid_company_name(text, firm_name):
            company_names.append(text)

    # Method 2: Image alt text
    # Some sites show only logos — the company name lives in the image's alt text
    if len(company_names) < 3:
        images = soup.find_all('img', alt=True)
        for img in images:
            alt = img['alt'].strip()
            if is_valid_company_name(alt, firm_name):
                company_names.append(alt)

    # Method 3: Scan links
    # Sometimes each company is a clickable link with their name as text
    if len(company_names) < 3:
        links = soup.find_all('a')
        for link in links:
            text = link.get_text(strip=True)
            if is_valid_company_name(text, firm_name):
                company_names.append(text)

    # Remove duplicates while keeping the original order
    seen = set()
    unique_companies = []
    for name in company_names:
        if name not in seen:
            seen.add(name)
            unique_companies.append(name)

    return unique_companies


# ============================================================
# HELPER — Is this actually a company name or just page junk?
# ============================================================
# When we scan headings we find things like "About Us", "Contact",
# "Read More" — not companies. This filters those out.

def is_valid_company_name(text, firm_name):

    if len(text) < 2 or len(text) > 60:
        return False

    junk_words = [
        'home', 'about', 'contact', 'team', 'news', 'blog', 'insights',
        'careers', 'jobs', 'press', 'media', 'login', 'search', 'menu',
        'privacy', 'terms', 'cookie', 'copyright', 'all rights', 'follow',
        'read more', 'learn more', 'view all', 'load more', 'subscribe',
        'newsletter', 'email', 'phone', 'address', 'linkedin', 'twitter',
        'facebook', 'instagram', 'youtube', 'strategy', 'approach', 'people',
        'leadership', 'fund', 'sector', 'region', 'asset', 'management',
        firm_name.lower()
    ]

    text_lower = text.lower()
    if any(junk in text_lower for junk in junk_words):
        return False

    if text.isdigit():
        return False

    # More than 6 words is probably a sentence, not a company name
    if len(text.split()) > 6:
        return False

    return True


# ============================================================
# MAIN — This is what runs when you start the program
# ============================================================

async def main():
    print("\n" + "=" * 55)
    print("  PE FIRM PORTFOLIO SCRAPER")
    print("  Type any PE firm name to get their investments")
    print("=" * 55)

    while True:
        firm_name = input("\n Enter PE firm name (or 'quit' to exit): ").strip()

        if firm_name.lower() in ['quit', 'exit', 'q']:
            print("Goodbye!")
            break

        if not firm_name:
            print("Please type a firm name first.")
            continue

        # Run the full pipeline
        companies = await scrape_portfolio(firm_name)

        # Display results
        print("\n" + "=" * 55)
        if companies:
            print(f" PORTFOLIO COMPANIES — {firm_name.upper()}")
            print("=" * 55)
            for i, company in enumerate(companies, 1):
                print(f"  {i:3}. {company}")
            print(f"\n  Total: {len(companies)} companies found")
        else:
            print(f" No companies found for '{firm_name}'")
            print("  The site may be blocking scrapers, or try a different name.")
        print("=" * 55)


# Start the program
if __name__ == "__main__":
    asyncio.run(main())
