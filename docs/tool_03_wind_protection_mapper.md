# Tool 3 – Wind Protection Mapper

## Description
Aggregates multiple windshade rasters (Tool 2 outputs) into:
1. Group rasters (maximum per detected direction group)
2. Final wind-protection raster (maximum across all groups)

Grouping is based on the first number found in filenames.

## Parameters
- Input folder (rasters)
- Recursive search (optional)
- File filter (glob; default `*.tif`)
- Ignore NoData (optional)
- Output folder
- Overwrite existing files (optional)

## Output
- Group-maximum rasters (e.g., `45_max.tif`)
- Final `wind_protection.tif`
