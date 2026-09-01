"""
Analysis layer: takes raw GEE images and produces the structured findings
that go straight into the report template (numbers, flags, short strings).
"""

import ee

from config import (
    NDWI_WET_THRESHOLD,
    HAND_FLOOD_RISK_M,
    WATER_OCCURRENCE_FLAG_PCT,
)

# ESA WorldCover class codes -> human labels
WORLDCOVER_CLASSES = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Bare/sparse vegetation",
    70: "Snow and ice",
    80: "Permanent water bodies",
    90: "Herbaceous wetland",
    95: "Mangroves",
    100: "Moss and lichen",
}


def lulc_change(aoi: ee.Geometry, wc_old: ee.Image, wc_new: ee.Image) -> dict:
    """
    Diff two WorldCover classifications over the same AOI and report the
    dominant class in each period plus any concerning transitions.
    """
    def class_histogram(img):
        hist = img.reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=aoi,
            scale=10,
            maxPixels=1e9,
        ).getInfo()
        # reduceRegion returns {'Map': {...}} for a single band sometimes;
        # normalize to a flat dict of class_code -> pixel_count
        band_name = list(hist.keys())[0]
        return {int(float(k)): v for k, v in hist[band_name].items()}

    old_hist = class_histogram(wc_old)
    new_hist = class_histogram(wc_new)

    def dominant(hist):
        if not hist:
            return "Unknown"
        code = max(hist, key=hist.get)
        return WORLDCOVER_CLASSES.get(code, f"Class {code}")

    old_dominant = dominant(old_hist)
    new_dominant = dominant(new_hist)

    built_up_old = old_hist.get(50, 0)
    built_up_new = new_hist.get(50, 0)
    built_up_increased = built_up_new > built_up_old * 1.2  # >20% growth in built pixels

    forest_old = old_hist.get(10, 0)
    forest_new = new_hist.get(10, 0)
    forest_cleared = forest_old > 0 and forest_new < forest_old * 0.8  # >20% loss

    flags = []
    if built_up_increased:
        flags.append("Built-up area expanded significantly over the lookback period.")
    if forest_cleared:
        flags.append("Tree cover declined significantly over the lookback period — possible clearing.")

    return {
        "dominant_class_old": old_dominant,
        "dominant_class_new": new_dominant,
        "changed": old_dominant != new_dominant,
        "flags": flags,
    }


def wetland_check(aoi: ee.Geometry, ndwi_image: ee.Image, gsw_image: ee.Image) -> dict:
    """
    Combine current NDWI with JRC historical water seasonality to catch
    land that reads dry today but was wet part of the year historically.
    """
    ndwi_mean = ndwi_image.select("NDWI").reduceRegion(
        reducer=ee.Reducer.mean(), geometry=aoi, scale=10, maxPixels=1e9
    ).get("NDWI").getInfo()

    occurrence_mean = gsw_image.select("occurrence").reduceRegion(
        reducer=ee.Reducer.mean(), geometry=aoi, scale=30, maxPixels=1e9
    ).get("occurrence")
    occurrence_mean = occurrence_mean.getInfo() if occurrence_mean is not None else 0

    currently_wet = (ndwi_mean or 0) > NDWI_WET_THRESHOLD
    historically_wet = (occurrence_mean or 0) > WATER_OCCURRENCE_FLAG_PCT

    flag = None
    if historically_wet and not currently_wet:
        flag = (
            f"Land appears dry today but was classified as water ~{occurrence_mean:.0f}% "
            "of the historical record — check for seasonal wetland or drainage issues."
        )
    elif currently_wet:
        flag = "Current imagery shows signs of standing water or saturated ground."

    return {
        "ndwi_mean": ndwi_mean,
        "historical_water_occurrence_pct": occurrence_mean,
        "currently_wet": currently_wet,
        "historically_wet": historically_wet,
        "flag": flag,
    }


def flood_risk(aoi: ee.Geometry, hand_image: ee.Image) -> dict:
    """Classify flood risk from HAND (height above nearest drainage) proxy."""
    hand_mean = hand_image.select("HAND").reduceRegion(
        reducer=ee.Reducer.mean(), geometry=aoi, scale=30, maxPixels=1e9
    ).get("HAND").getInfo()

    hand_min = hand_image.select("HAND").reduceRegion(
        reducer=ee.Reducer.min(), geometry=aoi, scale=30, maxPixels=1e9
    ).get("HAND").getInfo()

    at_risk = (hand_min or 999) < HAND_FLOOD_RISK_M

    if hand_mean is None:
        risk_level = "Unknown"
    elif hand_min < 3:
        risk_level = "High"
    elif hand_min < HAND_FLOOD_RISK_M:
        risk_level = "Moderate"
    else:
        risk_level = "Low"

    return {
        "hand_mean_m": hand_mean,
        "hand_min_m": hand_min,
        "risk_level": risk_level,
        "at_risk": at_risk,
    }


def encroachment_check(aoi: ee.Geometry, parcel_geom: ee.Geometry | None,
                        wc_new: ee.Image) -> dict:
    """
    If the buyer supplied a parcel boundary, check for built-up pixels
    that fall outside it but inside the surrounding AOI — a proxy for
    structures encroaching near the claimed boundary.
    """
    if parcel_geom is None:
        return {"checked": False, "note": "No parcel boundary supplied — skipped."}

    outside_parcel = aoi.difference(parcel_geom, ee.ErrorMargin(1))
    built_up = wc_new.eq(50)

    encroaching_px = built_up.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=outside_parcel,
        scale=10,
        maxPixels=1e9,
    ).get("Map")

    px_count = encroaching_px.getInfo() if encroaching_px is not None else 0
    approx_m2 = (px_count or 0) * 100  # 10m pixels

    return {
        "checked": True,
        "encroaching_area_m2": approx_m2,
        "flag": (
            f"~{approx_m2:.0f} m² of built-up area detected just outside the "
            "supplied parcel boundary — worth a ground-truth check."
            if approx_m2 > 200 else None
        ),
    }
