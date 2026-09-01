# Land Screening Report Pipeline

Generates a PDF land due-diligence report (LULC change, wetland check, flood risk,
encroachment) from free satellite/elevation data, for a given lat/lon.

## Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### Earth Engine auth

1. Create/select a Google Cloud project and enable the Earth Engine API.
2. Run once locally:
   ```bash
   earthengine authenticate
   ```
3. Set the project id as an env var:
   ```bash
   export GEE_PROJECT=imposing-elixir-479909-t2
   ```

⚠️ **Commercial use note:** Google Cloud project registration (with usage-based pricing
above the free quota) is required for all Earth Engine use, commercial included. Confirm
your expected volume stays in the free tier, or budget for it. If you'd rather avoid this
entirely, swap `gee_data.py`'s calls for the Copernicus Data Space Ecosystem API — the
Sentinel-2/SRTM sources are the same underlying data, just accessed without Google's ToS.

### Static map image (optional)

`report_generator._map_image` uses folium's PNG export, which needs a headless
Chrome + selenium under the hood:

```bash
pip install selenium
# plus a chromedriver on PATH, or set include_map=False (default) to skip it
```

## Usage

### CLI / one-off test
```bash
python report_generator.py
```

### Web UI
```bash
streamlit run app.py
```

## Project layout

```
land_report/
├── config.py              # thresholds, dataset IDs, defaults
├── gee_data.py             # all Earth Engine data pulls (S2, WorldCover, JRC water, SRTM, HAND)
├── analysis.py              # raw rasters -> report findings (LULC diff, wetland, flood, encroachment)
├── report_generator.py      # orchestrates pipeline, builds charts, renders PDF
├── templates/
│   └── report_template.html # Jinja2 HTML template, styled for WeasyPrint
├── app.py                   # Streamlit front-end
└── requirements.txt
```

## Known limitations to fix before charging real money

- **HAND computation** (`gee_data.compute_hand`) is a simplified elevation-percentile
  proxy, not true D8 flow-accumulation HAND. Swap in a precomputed HAND raster
  (e.g. from MERIT-Hydro) for anything beyond a rough screening signal.
- **ESA WorldCover** only has 2020/2021 editions publicly — for `years_back > 5` or so,
  the "old" LULC baseline is really just the earliest available edition, not a true
  historical layer. Consider training a lightweight Sentinel-2 classifier for older
  years if buyers care about longer horizons.
- **Encroachment check** assumes the buyer-supplied boundary is accurate; it can only
  ever be as good as that input.
- No caching layer — every report re-pulls raw imagery. Add a cache keyed on
  `(lat, lon, radius, years_back)` before this gets real traffic.
