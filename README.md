# QWERA Toolbox (QGIS)

**QWERA (QGIS Wind Erosion Risk Assessment)** is an open-source QGIS Processing toolbox
for spatial wind erosion risk assessment with explicit consideration of landscape
structures.

The toolbox implements the **WERA methodology** developed by Funk & Völker
(2023, 2024), which operationalizes **DIN 19706**, in a fully transparent,
reproducible, and non-proprietary QGIS environment.

QWERA was developed as part of a **Master’s thesis** and aims to provide a
scientifically sound reference implementation of WERA in QGIS using only
open-source components.

---

## Overview

![QWERA cover / logo](docs/img/cover_logo.png)

Wind erosion is a highly directional process controlled by wind climatology,
terrain exposure, soil properties, and landscape structure.
QWERA follows the conceptual definition:

**Wind erosion risk = Hazard × Exposure**

and implements this logic through a modular, GIS-based workflow.

---

## Toolbox structure

The QWERA toolbox is organized into additional tools (data preparation) and a main workflow (Tools 1–5).

![QWERA toolbox organigram](docs/img/fig2_toolbox_organigram.png)

---

## Installation (ZIP-based)

1. Download the latest release ZIP from the **Releases** section of this repository
2. Open QGIS
3. Navigate to **Plugins → Manage and Install Plugins → Install from ZIP**
4. Select the downloaded ZIP file and install the plugin
5. Enable the plugin if required
6. Open the **Processing Toolbox** to access all QWERA tools

---

## Example workflow

![Example workflow using the QWERA tools](docs/img/fig6_example_workflow.png)

---

## Documentation

The full user manual and detailed technical documentation are provided in the
`docs/` directory.

👉 Start here: [`docs/index.md`](docs/index.md)

---

## Citation

Funk, R. & Völker, L. (2024):  
*A GIS-toolbox for a landscape structure based Wind Erosion Risk Assessment (WERA).*  
MethodsX, 13, 103006  
https://doi.org/10.1016/j.mex.2024.103006

---

## License

GNU GPL v3 (GPL-3.0). See `LICENSE`.
