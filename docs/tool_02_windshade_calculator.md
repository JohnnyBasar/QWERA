# Tool 2 – Windshade Calculator

## Description
Generates wind-direction-specific shadow masks from a parameter table containing:
- Name / label
- Azimuth (°)
- Altitude (°)
- Constant (protection class)

For each row, a directional shadow mask raster is computed (octant-based horizon scan).

## Parameters
- Landscape elements raster (metric CRS)
- Parameter table (CSV / XLSX)
- Column mappings (name, azimuth, altitude, constant)
- Optional prefix/suffix
- Optional fat-shadows dilation
- Output folder

## Output
- One GeoTIFF per table row
  - Sunlit cells = 0
  - Shadowed cells = constant value
