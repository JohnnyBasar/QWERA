# Additional Tools

Additional tools support preprocessing and data preparation for the core workflow.

## ADF to GeoTIFF
Converts ArcGIS-style ADF rasters to GeoTIFF and resolves naming issues (bridge from WERA ArcGIS outputs).

## DWD Station Finder
Queries DWD stations providing wind data using:
- Name-based search
- Spatial filtering by extent
- Temporal resolution and wind mode filters
- Optional start/end period filters

## DWD Downloader (Just Data)
Downloads raw wind speed (FF) and direction (DD) from DWD Open Data via the `wetterdienst` API.
Exports summary CSV and optional combined/per-station raw CSVs.

## DWD Downloader and Wind Frequency Matrices Creator
Downloads and prepares DWD wind data and computes directional wind-frequency matrices:
- Recommended sectors: 8, 16, or 36 (36 recommended to avoid artefacts)
- Recommended speed bins: 1 m/s intervals
Exports matrices (overall, monthly, seasonal, custom) and optional windrose plots.

## Wind Frequency Matrices from Table
Computes wind-frequency matrices from an arbitrary input table (non-DWD datasets supported).

## Wind Shadow Parameters
Converts a custom aggregated wind matrix into WERA-style azimuth/altitude parameter tables for Tool 2.

## Soil Erodibility Mapper
Creates a soil-erodibility raster based on soil type/texture and SOM following DIN 19706 logic.
