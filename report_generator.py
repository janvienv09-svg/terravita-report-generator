"""
Ties the pipeline together: generate_report(lat, lon, radius_m, years_back) -> pdf_path
"""

import base64
import datetime as dt
import io
import uuid

import ee
import folium
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

import gee_data
import analysis
from config import DEFAULT_RADIUS_M, DEFAULT_YEARS_BACK

TEMPLATE_DIR = "templates"
TEMPLATE_NAME = "report_template.html"


def _fig_to_data_uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def _ndvi_chart(time_series: list) -> str:
    dates = [p["date"] for p in time_series]
    values = [p["value"] for p in time_series]
    fig, ax = plt.subplots(figsize=(7, 2.5))
    ax.plot(dates, values, marker="o", linewidth=2, color="#2b6cb0")
    ax.set_title("NDVI trend over lookback period")
    ax.set_ylabel("NDVI")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    return _fig_to_data_uri(fig)


def _map_image(lat: float, lon: float, radius_m: int) -> str:
    """
    Static folium map centered on the AOI. For a true LULC overlay,
    export a GEE thumbnail (Image.getThumbURL) and layer it in instead —
    left as a follow-up since it requires a signed URL round-trip.
    """
    m = folium.Map(location=[lat, lon], zoom_start=15, tiles="OpenStreetMap")
    folium.Circle(
        location=[lat, lon], radius=radius_m,
        color="#2b6cb0", fill=True, fill_opacity=0.15
    ).add_to(m)
    folium.Marker([lat, lon], tooltip="Site center").add_to(m)

    png_bytes = m._to_png(5)  # requires selenium; see README for headless setup
    encoded = base64.b64encode(png_bytes).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def generate_report(
    lat: float,
    lon: float,
    radius_m: int = DEFAULT_RADIUS_M,
    years_back: int = DEFAULT_YEARS_BACK,
    parcel_geojson: dict | None = None,
    output_path: str | None = None,
    include_map: bool = False,
) -> str:
    """
    Run the full pipeline for one plot and write a PDF report.
    Returns the path to the generated PDF.
    """
    gee_data.init_ee()

    end_date = dt.date.today()
    start_date = end_date.replace(year=end_date.year - years_back)
    end_str, start_str = end_date.isoformat(), start_date.isoformat()

    aoi = gee_data.make_aoi(lat, lon, radius_m)
    parcel_geom = ee.Geometry(parcel_geojson) if parcel_geojson else None

    # --- Pull data ---
    s2_recent = gee_data.get_s2_composite(
        aoi, end_date.replace(month=1, day=1).isoformat(), end_str
    )
    wc_old = gee_data.get_worldcover(aoi, year=start_date.year)
    wc_new = gee_data.get_worldcover(aoi, year=end_date.year)
    gsw = gee_data.get_surface_water(aoi)
    dem = gee_data.get_dem(aoi)
    hand_img = gee_data.compute_hand(aoi, dem)

    # --- Analyze ---
    lulc_result = analysis.lulc_change(aoi, wc_old, wc_new)
    wetland_result = analysis.wetland_check(aoi, s2_recent, gsw)
    flood_result = analysis.flood_risk(aoi, hand_img)
    encroachment_result = analysis.encroachment_check(aoi, parcel_geom, wc_new)

    # --- Time series for chart ---
    ndvi_series = gee_data.get_time_series_stats(aoi, "NDVI", start_str, end_str, step_months=12)
    ndvi_chart_uri = _ndvi_chart(ndvi_series) if any(p["value"] is not None for p in ndvi_series) else None

    map_uri = None
    if include_map:
        try:
            map_uri = _map_image(lat, lon, radius_m)
        except Exception:
            map_uri = None  # selenium/headless chrome not configured — skip gracefully

    area_hectares = round(3.14159 * (radius_m ** 2) / 10000, 1)

    # --- Render ---
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template(TEMPLATE_NAME)
    html_str = template.render(
        generated_date=dt.date.today().strftime("%B %d, %Y"),
        lat=round(lat, 5), lon=round(lon, 5), radius_m=radius_m,
        start_date=start_str, end_date=end_str,
        area_hectares=area_hectares,
        lulc=lulc_result,
        wetland=wetland_result,
        flood=flood_result,
        encroachment=encroachment_result,
        ndvi_chart=ndvi_chart_uri,
        map_image=map_uri,
        report_id=str(uuid.uuid4())[:8],
    )

    output_path = output_path or f"report_{lat}_{lon}.pdf".replace(" ", "")
    HTML(string=html_str, base_url=".").write_pdf(output_path)
    return output_path


if __name__ == "__main__":
    # Quick manual test — replace with real coordinates before running.
    path = generate_report(lat=37.8, lon=-122.3, radius_m=800, years_back=8)
    print(f"Report written to {path}")
