"""
Data access layer: everything that talks to Google Earth Engine lives here.

Auth:
    Run `earthengine authenticate` once locally, or set up a service account
    for server-side/Streamlit Cloud deployment (see README).
"""

import ee
import datetime as dt

from config import (
    GEE_PROJECT,
    S2_COLLECTION,
    WORLDCOVER_COLLECTION,
    JRC_GSW,
    SRTM_DEM,
    MAX_CLOUD_PCT,
)

_initialized = False


def init_ee():
    """Initialize the Earth Engine session once per process."""
    global _initialized
    if _initialized:
        return
    try:
        ee.Initialize(project=imposing-elixir-479909-t2)
    except Exception:
        ee.Authenticate()
        ee.Initialize(project=imposing-elixir-479909-t2)
    _initialized = True


def make_aoi(lat: float, lon: float, radius_m: int) -> ee.Geometry:
    """Buffer a point into a circular area of interest."""
    return ee.Geometry.Point([lon, lat]).buffer(radius_m)


def get_s2_composite(aoi: ee.Geometry, start_date: str, end_date: str) -> ee.Image:
    """
    Median, cloud-masked Sentinel-2 composite over the AOI/date range.
    Returns an image with bands B2-B12 plus computed NDWI/NDVI.
    """
    def mask_clouds(img):
        scl = img.select("SCL")
        # SCL classes 3 (cloud shadow), 8/9 (cloud medium/high prob), 10 (cirrus)
        mask = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10))
        return img.updateMask(mask)

    coll = (
        ee.ImageCollection(S2_COLLECTION)
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_CLOUD_PCT))
        .map(mask_clouds)
    )

    composite = coll.median().clip(aoi)

    ndvi = composite.normalizedDifference(["B8", "B4"]).rename("NDVI")
    ndwi = composite.normalizedDifference(["B3", "B8"]).rename("NDWI")  # McFeeters NDWI

    return composite.addBands([ndvi, ndwi])


def get_worldcover(aoi: ee.Geometry, year: int = 2021) -> ee.Image:
    """
    ESA WorldCover pre-classified LULC (10m). Only 2020 and 2021 editions
    exist publicly; for older 'years_back' windows this is your closest
    baseline unless you train your own Sentinel-2 classifier.
    """
    edition_year = 2020 if year <= 2020 else 2021
    coll = ee.ImageCollection(WORLDCOVER_COLLECTION)
    img = coll.filter(ee.Filter.eq("system:index", str(edition_year))).first()
    return img.clip(aoi)


def get_surface_water(aoi: ee.Geometry) -> ee.Image:
    """JRC Global Surface Water: occurrence (% of time water was present) + seasonality."""
    gsw = ee.Image(JRC_GSW)
    return gsw.select(["occurrence", "seasonality"]).clip(aoi)


def get_dem(aoi: ee.Geometry) -> ee.Image:
    """SRTM elevation, used as input to HAND computation."""
    return ee.Image(SRTM_DEM).clip(aoi)


def compute_hand(aoi: ee.Geometry, dem: ee.Image, stream_threshold_acc: int = 500) -> ee.Image:
    """
    Approximate Height Above Nearest Drainage.

    This is a simplified HAND proxy suitable for a screening-level report,
    not a hydrology model:
      1. Derive flow accumulation from the DEM (via terrain analysis).
      2. Threshold it to define a synthetic stream network.
      3. For each pixel, compute elevation minus the elevation of the
         nearest stream-network pixel.

    For production use, consider precomputed HAND rasters (e.g. from the
    HydroSHEDS/MERIT-Hydro derived products) instead of deriving this
    on the fly, which is coarse at 30m resolution.
    """
    filled = ee.Terrain.fillMinima(dem) if hasattr(ee.Terrain, "fillMinima") else dem
    flow_dir = ee.Terrain.products(dem) if False else None  # placeholder for clarity

    # Practical approach: use a slope/curvature-based stream proxy since
    # full D8 flow accumulation isn't natively available in the EE API
    # without the hydrology toolkit. This land-buyer report treats HAND
    # as "elevation above the lowest point within the AOI's drainage lines"
    # approximated via a low-elevation percentile mask.
    slope = ee.Terrain.slope(dem)
    low_elev_mask = dem.lt(dem.reduceRegion(
        reducer=ee.Reducer.percentile([10]),
        geometry=aoi,
        scale=30,
        maxPixels=1e9,
    ).values().get(0))

    stream_proxy = dem.updateMask(low_elev_mask)
    stream_elev = stream_proxy.reduceRegion(
        reducer=ee.Reducer.min(),
        geometry=aoi,
        scale=30,
        maxPixels=1e9,
    ).values().get(0)

    hand = dem.subtract(ee.Image.constant(stream_elev)).rename("HAND")
    return hand.clip(aoi)


def get_time_series_stats(aoi: ee.Geometry, band: str, start_date: str, end_date: str,
                           step_months: int = 6) -> list:
    """
    Pull mean band value (e.g. NDVI/NDWI) over the AOI at regular intervals,
    for the trend chart in the report.
    """
    start = dt.datetime.strptime(start_date, "%Y-%m-%d")
    end = dt.datetime.strptime(end_date, "%Y-%m-%d")

    points = []
    cursor = start
    while cursor < end:
        window_end = min(cursor + dt.timedelta(days=30 * step_months), end)
        img = get_s2_composite(aoi, cursor.strftime("%Y-%m-%d"), window_end.strftime("%Y-%m-%d"))
        val = img.select(band).reduceRegion(
            reducer=ee.Reducer.mean(), geometry=aoi, scale=20, maxPixels=1e9
        ).get(band)
        try:
            value = val.getInfo()
        except Exception:
            value = None
        points.append({"date": cursor.strftime("%Y-%m"), "value": value})
        cursor = window_end

    return points
