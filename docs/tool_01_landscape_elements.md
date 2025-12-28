# Tool 1 – Landscape Elements Calculator

## Description
Computes a landscape-element height raster by subtracting a **DEM** from a **DSM**.
The result represents above-ground structures such as vegetation, hedges, or buildings.

Optionally, a polygon layer (e.g., field blocks) can be used to set cells within polygons to zero
to remove non-permanent obstacles in agricultural areas.

## Parameters
- DEM (reference grid)
- DSM (surface model; reprojected to DEM if needed)
- Polygon layer (optional; set cells within polygons to 0)
- Output raster

## Output
- Landscape elements raster (DSM − DEM), Float32, aligned to DEM grid
