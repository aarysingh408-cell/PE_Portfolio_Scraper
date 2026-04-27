import streamlit as st
import asyncio
from scraper import scrape_portfolio

# ── Page config ──────────────────────────────────────────────
st.set_page_config(
    page_title="PE Portfolio Finder",
    page_icon="🔍",
    layout="centered"
)

# ── Custom styling ────────────────────────────────────────────
st.markdown("""
<style>
    .main { max-width: 720px; margin: auto; }
    .stButton > button {
        width: 100%;
        background-color: #1a1a2e;
        color: white;
        border: none;
        padding: 0.6rem 1.5rem;
        font-size: 16px;
        border-radius: 8px;
        margin-top: 8px;
    }
    .stButton > button:hover { background-color: #16213e; }
    .company-count {
        text-align: center;
        color: #888;
        font-size: 14px;
        margin: 16px 0 8px;
    }
    .firm-badge {
        display: inline-block;
        background: #f0f4ff;
        color: #1a1a2e;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 13px;
        margin-bottom: 16px;
    }
</style>
""", unsafe_allow_html=True)


# ── Header ────────────────────────────────────────────────────
st.markdown("## 🔍 PE Portfolio Finder")
st.markdown("Type any private equity firm name and get a list of all companies they have invested in.")
st.markdown("---")


# ── Input ─────────────────────────────────────────────────────
firm_name = st.text_input(
    label="Private Equity Firm Name",
    placeholder="e.g. Chrys Capital, Sequoia India, Kedaara Capital...",
    label_visibility="visible"
)

search_clicked = st.button("🔍 Search Portfolio")


# ── Run scraper when button is clicked ────────────────────────
if search_clicked:

    if not firm_name.strip():
        st.warning("Please enter a firm name first.")

    else:
        # Show a spinner while scraping — so users know it's working
        with st.spinner(f"Searching for {firm_name}'s portfolio... this takes 20–40 seconds..."):
            try:
                # Run the async scraper
                companies = asyncio.run(scrape_portfolio(firm_name.strip()))
            except Exception as e:
                companies = []
                st.error(f"Something went wrong: {e}")

        # ── Show results ──────────────────────────────────────
        if companies:
            st.success(f"Found {len(companies)} companies in {firm_name}'s portfolio!")
            st.markdown("---")

            # Download button — lets users save as CSV
            csv_content = "Company Name\n" + "\n".join(companies)
            st.download_button(
                label="⬇️ Download as CSV",
                data=csv_content,
                file_name=f"{firm_name.replace(' ', '_')}_portfolio.csv",
                mime="text/csv"
            )

            st.markdown(f"<div class='company-count'>{len(companies)} companies found for <strong>{firm_name}</strong></div>", unsafe_allow_html=True)

            # Show companies in a clean 2-column grid
            col1, col2 = st.columns(2)
            for i, company in enumerate(companies):
                if i % 2 == 0:
                    col1.markdown(f"**{i+1}.** {company}")
                else:
                    col2.markdown(f"**{i+1}.** {company}")

        else:
            st.error(f"No companies found for '{firm_name}'.")
            st.markdown("""
            **Try these tips:**
            - Check the spelling of the firm name
            - Try a shorter version of the name (e.g. "Chrys" instead of "Chrys Capital")
            - Some firm websites block automated access — try another firm
            """)


# ── Footer ────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<div style='text-align:center;color:#aaa;font-size:12px;'>"
    "Built by Integraate Innovations &nbsp;|&nbsp; Data sourced live from firm websites"
    "</div>",
    unsafe_allow_html=True
)
