# Tool 5 – Field Blocks Statistics

## Description
Calculates, for each polygon (e.g., field block), the proportion of area exceeding a user-defined
susceptibility threshold using the Tool 4 output raster.

## Parameters
- Susceptibility/risk raster (Tool 4 output)
- Polygon layer (field blocks)
- Threshold (default: 5)
- Output vector layer

## Output attributes
- `risk_count`: total number of raster cells evaluated within polygon
- `risk_sum`: number of raster cells ≥ threshold
- `area_m2`: polygon area (m²)
- `area_high_m2`: area of pixels ≥ threshold (m²)
- `pct_high`: share (%) of high-risk area
- `thr_val`: threshold used
