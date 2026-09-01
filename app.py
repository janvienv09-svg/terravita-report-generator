"""
Streamlit MVP: paste coordinates -> get a PDF land screening report.

Run with: streamlit run app.py
"""

import streamlit as st
from report_generator import generate_report
from config import DEFAULT_RADIUS_M, DEFAULT_YEARS_BACK

st.set_page_config(page_title="Land Screening Report", page_icon="🛰️")

st.title("🛰️ Land Screening Report")
st.caption(
    "Satellite-derived land-use change, wetland, and flood-risk screening — "
    "not a substitute for a licensed survey or title search."
)

with st.form("report_form"):
    col1, col2 = st.columns(2)
    with col1:
        lat = st.number_input("Latitude", value=37.8000, format="%.6f")
    with col2:
        lon = st.number_input("Longitude", value=-122.3000, format="%.6f")

    radius_m = st.slider("Analysis radius (meters)", 100, 5000, DEFAULT_RADIUS_M, step=100)
    years_back = st.slider("Lookback period (years)", 2, 20, DEFAULT_YEARS_BACK)
    include_map = st.checkbox("Include static map image (requires headless Chrome)", value=False)

    submitted = st.form_submit_button("Generate Report")

if submitted:
    with st.spinner("Pulling satellite data and building your report — this can take 30-90s..."):
        try:
            pdf_path = generate_report(
                lat=lat,
                lon=lon,
                radius_m=radius_m,
                years_back=years_back,
                include_map=include_map,
                output_path="latest_report.pdf",
            )
            st.success("Report generated.")
            with open(pdf_path, "rb") as f:
                st.download_button(
                    "Download PDF Report",
                    data=f,
                    file_name="land_screening_report.pdf",
                    mime="application/pdf",
                )
        except Exception as e:
            st.error(f"Something went wrong: {e}")
            st.info(
                "Common causes: Earth Engine not authenticated, GEE_PROJECT not set, "
                "or no cloud-free Sentinel-2 imagery available for this area/period."
            )
