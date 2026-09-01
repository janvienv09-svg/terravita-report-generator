"""
Central config for the land due-diligence report pipeline.

GEE_PROJECT: your Google Cloud project ID registered for Earth Engine
             (required for all EE use as of 2024, commercial included).
             See: https://developers.google.com/earth-engine/guides/access
"""

import os

GEE_PROJECT = os.environ.get("GEE_PROJECT", "your-gcp-project-id")

# Sentinel-2 surface reflectance collection
S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"

# ESA WorldCover pre-classified land use/land cover (10m, 2020 & 2021 editions)
WORLDCOVER_COLLECTION = "ESA/WorldCover/v200"

# JRC Global Surface Water — historical water occurrence / seasonality
JRC_GSW = "JRC/GSW1_4/GlobalSurfaceWater"

# SRTM 30m DEM, used to derive HAND (height above nearest drainage)
SRTM_DEM = "USGS/SRTMGL1_003"

# Cloud filter threshold for Sentinel-2 composites
MAX_CLOUD_PCT = 20

# Default report parameters
DEFAULT_RADIUS_M = 1000
DEFAULT_YEARS_BACK = 10

# Risk thresholds — tune these against real parcels before relying on them
NDWI_WET_THRESHOLD = 0.0        # NDWI > 0 generally indicates open water/saturated soil
HAND_FLOOD_RISK_M = 10          # height above nearest drainage, in meters
WATER_OCCURRENCE_FLAG_PCT = 25  # % of time historically classified as water
