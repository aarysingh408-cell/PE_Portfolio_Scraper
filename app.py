import streamlit as st
import asyncio
import subprocess
import sys
from scraper import scrape_portfolio

@st.cache_resource
def install_playwright_browser():
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True
    )

install_playwright_browser()

st.set_page_config(
    page_title="PE Portfolio Finder",
    page_icon="🔍",
    layout="centered"
)

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
        gap: 16px;
    }
    .ask-gold-bar {
        width: 4px;
        min-height: 46px;
        background-color: #BB962C;
        border-radius: 2px;
        flex-shrink: 0;
    }
    .ask-header-title {
        font-size: 20px;
        font-weight: 600;
        color: white;
        margin: 0 0 4px;
    }
    .ask-header-sub {
        font-size: 13px;
        color: rgba(255,255,255,0.6);
        margin: 0;
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
    .stButton > button:hover {
        background-color: #044f65;
        color: white;
        border: none;
    }
    .company-count {
        text-align: center;
        color: #58595B;
        font-size: 14px;
        margin: 16px 0 12px;
    }
    .ask-footer {
        text-align: center;
        color: #aaa;
        font-size: 12px;
        margin-top: 40px;
        padding-top: 16px;
        border-top: 1px solid #f0f0f0;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="ask-header">
    <div class="ask-gold-bar"></div>
    <div>
        <p class="ask-header-title">PE Portfolio Finder</p>
        <p class="ask-header-sub">Type any private equity firm name — get a full list of their investments</p>
    </div>
</div>
""", unsafe_allow_html=True)

firm_name = st.text_input(
    label="Private equity firm name",
    placeholder="e.g. Chrys Capital, Sequoia India, Kedaara Capital, Blackstone...",
)

search_clicked = st.button("Search Portfolio")

if search_clicked:
    if not firm_name.strip():
        st.warning("Please enter a firm name first.")
    else:
        with st.spinner(f"Searching {firm_name}'s portfolio... takes 20-40 seconds..."):
            try:
                companies = asyncio.run(scrape_portfolio(firm_name.strip()))
            except Exception as e:
                companies = []
                st.error(f"Something went wrong: {e}")

        if companies:
            st.success(f"Found {len(companies)} companies in {firm_name}'s portfolio")
            st.markdown("---")
            csv_content = "Company Name\n" + "\n".join(companies)
            st.download_button(
                label="Download as CSV",
                data=csv_content,
                file_name=f"{firm_name.replace(' ', '_')}_portfolio.csv",
                mime="text/csv"
            )
            st.markdown(
                f"<div class='company-count'>{len(companies)} companies found for <strong>{firm_name}</strong></div>",
                unsafe_allow_html=True
            )
            col1, col2 = st.columns(2)
            for i, company in enumerate(companies):
                if i % 2 == 0:
                    col1.markdown(f"**{i+1}.** {company}")
                else:
                    col2.markdown(f"**{i+1}.** {company}")
        else:
            st.error(f"No companies found for '{firm_name}'.")
            st.markdown("""
            **Tips:**
            - Double check the spelling
            - Try a shorter name e.g. "Kedaara" instead of "Kedaara Capital"
            - Some firm websites block automated tools — try a different firm
            """)

st.markdown(
    "<div class='ask-footer'>Built by Aaryaman Singh &nbsp;·&nbsp; Data sourced live from firm websites</div>",
    unsafe_allow_html=True
)
