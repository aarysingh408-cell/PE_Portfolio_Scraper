# ============================================================
#  ASK Eve — SEBI DRHP Section Extractor
#  Searches SEBI, downloads DRHP, extracts key sections
# ============================================================

import asyncio
import re
import io
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from pypdf import PdfReader, PdfWriter

SEBI_LISTING_URL = "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=3&ssid=15&smid=10"
SEBI_BASE        = "https://www.sebi.gov.in"

# ── Section extraction limits ────────────────────────────────
SECTION_LIMITS = {
    "business":   25,
    "risk":       20,
    "promoters":  20,
    "objects":    10,
    "financials": 35,
}

SECTION_LABELS = {
    "business":   "Company Overview / Our Business",
    "risk":       "Risk Factors",
    "promoters":  "Promoters & Promoter Group",
    "objects":    "Objects of the Offer",
    "financials": "Financial Information",
}

SECTION_KEYWORDS = {
    "business":   ["OUR BUSINESS", "BUSINESS OVERVIEW", "ABOUT OUR COMPANY"],
    "risk":       ["RISK FACTORS"],
    "promoters":  ["OUR PROMOTERS AND PROMOTER GROUP", "PROMOTERS AND PROMOTER GROUP", "OUR PROMOTERS"],
    "objects":    ["OBJECTS OF THE OFFER", "OBJECTS OF THE ISSUE", "USE OF PROCEEDS"],
    "financials": ["RESTATED CONSOLIDATED FINANCIAL", "RESTATED FINANCIAL STATEMENTS",
                   "RESTATED FINANCIAL INFORMATION", "FINANCIAL INFORMATION", "FINANCIAL STATEMENTS"],
}

TOC_PATTERNS = {
    "business": [
        r"OUR\s+BUSINESS\s*[.\s]+(\d+)",
        r"BUSINESS\s+OVERVIEW\s*[.\s]+(\d+)",
        r"ABOUT\s+OUR\s+COMPANY\s*[.\s]+(\d+)",
    ],
    "risk": [
        r"RISK\s+FACTORS\s*[.\s]+(\d+)",
    ],
    "promoters": [
        r"OUR\s+PROMOTERS\s+AND\s+PROMOTER\s+GROUP\s*[.\s]+(\d+)",
        r"PROMOTERS\s+AND\s+PROMOTER\s+GROUP\s*[.\s]+(\d+)",
        r"PROMOTER\s+AND\s+PROMOTER\s+GROUP\s*[.\s]+(\d+)",
        r"OUR\s+PROMOTERS\s*[.\s]+(\d+)",
    ],
    "objects": [
        r"OBJECTS\s+OF\s+THE\s+(?:OFFER|ISSUE|FRESH\s+ISSUE)\s*[.\s]+(\d+)",
        r"USE\s+OF\s+(?:NET\s+)?PROCEEDS\s*[.\s]+(\d+)",
    ],
    "financials": [
        r"RESTATED\s+CONSOLIDATED\s+FINANCIAL\s+(?:INFORMATION|STATEMENTS)\s*[.\s]+(\d+)",
        r"RESTATED\s+(?:STANDALONE\s+)?FINANCIAL\s+(?:INFORMATION|STATEMENTS)\s*[.\s]+(\d+)",
        r"SECTION\s+V[:\s]*FINANCIAL\s+INFORMATION\s*[.\s]+(\d+)",
        r"FINANCIAL\s+(?:INFORMATION|STATEMENTS)\s*[.\s]+(\d+)",
    ],
}


# ============================================================
#  STEP 1 — Search SEBI for matching DRHPs
# ============================================================

async def search_sebi(query: str) -> list:
    """
    Search SEBI DRHP listing page for companies matching query.
    Returns list of {name, date, url} dicts.
    """
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
                  "--disable-background-networking"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}
        )
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,mp4}",
                         lambda route: route.abort())
        try:
            await page.goto(SEBI_LISTING_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

            # Fill search box — try different selectors
            for sel in ["input[name='query']", "input[type='text']",
                        "input[placeholder*='Search']", "input[placeholder*='Title']"]:
                try:
                    inp = page.locator(sel).first
                    if await inp.is_visible(timeout=1000):
                        await inp.fill(query)
                        break
                except: continue

            # Click GO
            for sel in ["a:has-text('GO')", "input[value='GO']",
                        "button:has-text('GO')", "[onclick*='searchFormNewsList']"]:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=1000):
                        await btn.click()
                        break
                except: continue

            await page.wait_for_timeout(3000)

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            # Parse results table
            table = soup.find("table")
            if table:
                for row in table.find_all("tr"):
                    cells = row.find_all("td")
                    if len(cells) < 2:
                        continue
                    date_text = cells[0].get_text(strip=True)
                    title_cell = cells[1]

                    # Get first link in the cell (main DRHP link)
                    link = title_cell.find("a")
                    if not link:
                        continue
                    href = link.get("href", "")
                    if not href or ".html" not in href:
                        continue

                    full_url = href if href.startswith("http") else SEBI_BASE + href
                    raw_name = link.get_text(strip=True)

                    # Clean name — remove "- DRHP", "- Draft Abridged Prospectus" etc.
                    clean_name = re.sub(
                        r"\s*[-–]\s*(?:DRHP|Draft Offer|Draft Abridged|Corrigendum|Addendum).*$",
                        "", raw_name, flags=re.IGNORECASE
                    ).strip()
                    if not clean_name:
                        continue

                    results.append({
                        "name": clean_name,
                        "date": date_text,
                        "url":  full_url,
                    })

        except Exception as e:
            print(f"SEBI search error: {e}")
        finally:
            await context.close()
            await browser.close()

    return results


# ============================================================
#  STEP 2 — Get PDF download URL from company page
# ============================================================

async def get_pdf_url(company_page_url: str) -> str:
    """
    Visit the SEBI company page and extract the direct PDF URL.
    """
    pdf_url = None

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        # Intercept network requests to catch PDF URLs
        pdf_urls_found = []
        async def handle_request(request):
            if ".pdf" in request.url.lower():
                pdf_urls_found.append(request.url)
        page.on("request", handle_request)

        try:
            await page.goto(company_page_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            # Method 1: iframe src with .pdf
            for tag in soup.find_all(["iframe", "embed", "object"]):
                src = tag.get("src", "") or tag.get("data", "")
                if ".pdf" in src.lower():
                    pdf_url = src if src.startswith("http") else SEBI_BASE + src
                    break

            # Method 2: Links to .pdf that are NOT abridged prospectus
            if not pdf_url:
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    if ".pdf" in href.lower():
                        # Prefer main DRHP over abridged (_p.pdf)
                        if "_p.pdf" not in href:
                            pdf_url = href if href.startswith("http") else SEBI_BASE + href
                            break

            # Method 3: Any .pdf link
            if not pdf_url:
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    if ".pdf" in href.lower():
                        pdf_url = href if href.startswith("http") else SEBI_BASE + href
                        break

            # Method 4: PDF URL intercepted from network
            if not pdf_url and pdf_urls_found:
                # Prefer larger/main DRHP over abridged
                for url in pdf_urls_found:
                    if "_p.pdf" not in url:
                        pdf_url = url
                        break
                if not pdf_url:
                    pdf_url = pdf_urls_found[0]

            # Method 5: Scan JavaScript for PDF paths
            if not pdf_url:
                for script in soup.find_all("script"):
                    if script.string:
                        matches = re.findall(r'["\']([^"\']*sebi[^"\']*\.pdf)["\']',
                                             script.string, re.IGNORECASE)
                        if matches:
                            m = matches[0]
                            pdf_url = m if m.startswith("http") else SEBI_BASE + m
                            break

        except Exception as e:
            print(f"PDF URL error: {e}")
        finally:
            await context.close()
            await browser.close()

    return pdf_url


# ============================================================
#  STEP 3 — Download PDF to memory
# ============================================================

def download_pdf(pdf_url: str) -> bytes:
    """Download PDF bytes from URL."""
    headers = {
        "User-Agent":  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer":     SEBI_BASE + "/",
        "Accept":      "application/pdf,*/*",
    }
    resp = requests.get(pdf_url, headers=headers, timeout=120, stream=True)
    resp.raise_for_status()

    chunks = []
    for chunk in resp.iter_content(chunk_size=1024 * 1024):
        if chunk:
            chunks.append(chunk)
    return b"".join(chunks)


# ============================================================
#  STEP 4 — Parse TOC to find section page numbers
# ============================================================

def parse_toc(pdf_bytes: bytes) -> dict:
    """
    Read first 15 pages of PDF and extract TOC page numbers
    for each target section.
    Returns {section_key: toc_page_number}
    """
    reader    = PdfReader(io.BytesIO(pdf_bytes))
    total     = len(reader.pages)
    toc_text  = ""

    for i in range(min(15, total)):
        try:
            toc_text += reader.pages[i].extract_text() + "\n"
        except:
            continue

    found = {}
    for section, patterns in TOC_PATTERNS.items():
        for pat in patterns:
            m = re.search(pat, toc_text, re.IGNORECASE | re.DOTALL)
            if m:
                found[section] = int(m.group(1))
                break

    return found, total


# ============================================================
#  STEP 5 — Find actual PDF page index for a TOC page number
# ============================================================

def find_page_index(reader: PdfReader, toc_page: int, keywords: list, total_pages: int) -> int:
    """
    DRHPs have preliminary pages (cover, disclaimer etc.) before page 1.
    Search for the actual page containing a keyword near the expected location.
    """
    # Search window: toc_page ± 40 pages (covers most offsets)
    search_start = max(0, toc_page - 5)
    search_end   = min(total_pages - 1, toc_page + 50)

    for i in range(search_start, search_end):
        try:
            text = reader.pages[i].extract_text() or ""
            for kw in keywords:
                if kw.upper() in text.upper():
                    return i
        except:
            continue

    # Fallback — use toc_page directly (0-indexed)
    return min(toc_page, total_pages - 1)


# ============================================================
#  STEP 6 — Extract sections and build output PDF
# ============================================================

def extract_sections(pdf_bytes: bytes) -> tuple:
    """
    Main extraction function.
    Returns (output_pdf_bytes, extraction_log_list)
    """
    toc_pages, total_pages = parse_toc(pdf_bytes)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    log    = []

    section_order = ["business", "risk", "promoters", "objects", "financials"]

    for section in section_order:
        label    = SECTION_LABELS[section]
        keywords = SECTION_KEYWORDS[section]
        limit    = SECTION_LIMITS[section]

        if section not in toc_pages:
            log.append(f"⚠️  {label} — not found in Table of Contents")
            continue

        toc_page  = toc_pages[section]
        start_idx = find_page_index(reader, toc_page, keywords, total_pages)
        end_idx   = min(start_idx + limit, total_pages)

        count = 0
        for idx in range(start_idx, end_idx):
            try:
                writer.add_page(reader.pages[idx])
                count += 1
            except:
                continue

        log.append(f"✅  {label} — {count} pages (DRHP pages ~{start_idx + 1}–{end_idx})")

    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)

    return buf.getvalue(), log
