# Methodological Background

Wind erosion is driven by interactions among atmospheric flow, soil properties, land use, and landscape structure.
QWERA is based on **DIN 19706:2013-02** and the GIS workflow proposed by **Funk & Völker (2023, 2024)**.

## DIN 19706:2013-02
DIN 19706:2013-02 defines a structured framework for wind-erosion assessment, including:
- Soil properties (soil type/ SOM)
- Soil erodibility
- Surface properties / land use effects
- Topographic exposure

## WERA (Funk & Völker)
WERA translates DIN 19706 into GIS-ready modules:
- Wind-frequency matrices (direction sectors, speed bins)
- Landscape-element shelter effects (porosity, shelter distance)
- Terrain-based shadow/exposure modelling (azimuth/altitude logic)
- Modular model logic for transparency and reproducibility

## QWERA integration
QWERA translates these concepts into QGIS:
- DIN defines **what** must be assessed; WERA defines **how** it is computed
- Directional modelling is central (wind + terrain)
- Risk is interpreted as **Hazard × Exposure**

## Planning capabilities
- By manually changing raster values within the LE raster (Tool 2; e.g., to simulate a hedge row), the hypothetical wind protection can be revised   
