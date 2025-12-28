# Methodological Background

Wind erosion is driven by interactions among atmospheric flow, soil properties, land use, and landscape structure.
QWERA is based on **DIN 19706:2013-02** and the GIS workflow proposed by **Funk & Völker (2023, 2024)**.

## DIN 19706
DIN 19706 defines a structured framework for wind-erosion assessment, including:
- Threshold wind speed
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
