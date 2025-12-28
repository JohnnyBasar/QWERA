

# -*- coding: utf-8 -*-
"""
Tool 3: Wind Protection Mapper
"""

import re
from pathlib import Path
from typing import Dict, List, Iterable
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFile,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterString,
    QgsProcessingParameterFolderDestination,
    QgsProcessingException,
    QgsProcessingContext,
    QgsProcessingFeedback,
)
from qgis.core import QgsProject
from qgis import processing
import os

class wind_protection_classes(QgsProcessingAlgorithm):
    # Parameter-Keys
    INPUT_DIR = "INPUT_DIR"
    RECURSIVE = "RECURSIVE"
    GLOB = "GLOB"
    IGNORE_NODATA = "IGNORE_NODATA"
    OUTPUT_DIR = "OUTPUT_DIR"
    OVERWRITE = "OVERWRITE"

    # Regex: erste Zahl im Dateinamen
    FIRST_NUMBER = re.compile(r"^[^\d]*(\d+)")

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_DIR,
                "Input folder containing rasters",
                behavior=QgsProcessingParameterFile.Folder,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.RECURSIVE, "Search subfolders recursively", defaultValue=True
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.GLOB,
                "File filter (glob pattern)",
                defaultValue="*.tif",
                multiLine=False,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.IGNORE_NODATA, "Ignore NoData", defaultValue=True
            )
        )
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_DIR, "Output folder"
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.OVERWRITE, "Overwrite existing files", defaultValue=False
            )
        )

    def icon(self):
    # Pfad relativ zu diesem Dateiordner
        icon_path = os.path.join(os.path.dirname(__file__), "..", "icons", "qwera_tool_3.svg")
        return QIcon(icon_path)

    def name(self):
        return "wind_protection_classes"

    def displayName(self):
        return "Tool 3: Wind protection Mapper"

    # def group(self): 
    #     return ("Tool 3: Wind Protection Tools")
    
    # def groupId(self): 
    #     return "tool_3"
    
    def shortHelpString(self):
        return """
            <p>
            This tool groups multiple raster layers (wind-protection masks) by the first number in their filename (e.g. wind directions comming from Tool 2) and computes, for each group, a new raster that contains the cell-wise maximum across all group members.
            It is typically applied after <i>Tool 2: Windshade Calculator</i> to merge windshadow masks into composite wind-protection layers. The tool scans for raster files (default: <code>*.tif</code>), optionally including subfolders. each file’s name is inspected for the <i>first numeric substring</i>; all rasters sharing that number form one group (e.g. <code>r45a_...</code> → group 45).
            </p>

            <h2>Standards & References</h2>
            <dt><ul>
            <li><b><a href="https://www.sciencedirect.com/science/article/pii/S2215016124004576">Funk &amp; V&ouml;lker (2024)</a></b>, “A GIS-toolbox for a landscape structure based Wind Erosion Risk Assessment (WERA)” — describes the methodological context of using DWD wind statistics for erosion risk modeling. Within every group, the tool calculates a new raster whose pixel values are the maximum across all inputs of that group. all group results are again merged into one overall maximum raster (<code>wind_protection.tif</code>).
            <li><b>QGIS native:cellstatistics</b> — used to compute per-cell maxima across grouped rasters.</li>
            </ul></dt>


            <h2>Inputs</h2>
            <dt><ul>
            <li><b>Input folder</b> — directory containing GeoTIFF rasters to be processed.</li>
            <li><b>Search subfolders</b> — toggle recursive file search.</li>
            <li><b>File filter (glob)</b> — pattern for matching input files (e.g. <code>*.tif</code>).</li>
            <li><b>Ignore NoData</b> — decides whether NoData cells participate in the cell-wise maximum calculation.</li>
            <li><b>Output folder</b> — destination directory for group and final rasters.</li>
            <li><b>Overwrite existing</b> — if enabled, existing results with identical names will be replaced.</li>
            </ul></dt>

            <h2>Outputs</h2>
            <dt><ul>
            <li><b>Group-maximum rasters</b> — one file per detected group (e.g. <code>45_max.tif</code>).</li>
            <li><b>Combined maximum raster</b> — <code>wind_protection.tif</code>, the overall maximum of all groups.</li>
            <li>All rasters preserve the grid of their reference layer; CRS and resolution remain unchanged.</li>
            </ul></dt>

            <h2>Notes</h2>
            <dt><ul>
            <li>Input filenames must contain a leading number if grouping by numeric prefix is intended (e.g. r45a_hs_az45_alt36.tif  -> group prefix: 45).</li>
            <li>All rasters within a group should share the same grid geometry (extent, CRS, cell size).</li>
            <li>The algorithm uses <code>STATISTIC = Maximum</code> (7) within <code>native:cellstatistics</code>.</li>
            <li>ChatGPT was used to create this plugin.</li>
            <li>Tested with QGIS 3.44.x (Python 3.12, Windows).</li>
            </ul></dt>
        """

    def createInstance(self):
        return wind_protection_classes()
    # ---------- Hilfsfunktionen ----------

    def _iter_files(self, root: Path, glob: str, recursive: bool) -> Iterable[Path]:
        it = root.rglob(glob) if recursive else root.glob(glob)
        for p in it:
            if p.is_file():
                yield p

    def _group_by_first_number(self, files: Iterable[Path]) -> Dict[str, List[str]]:
        groups: Dict[str, List[str]] = {}
        for f in files:
            m = self.FIRST_NUMBER.match(f.stem)
            key = m.group(1) if m else f.stem  # Fallback: kompletter Name, falls keine Zahl vorhanden
            groups.setdefault(key, []).append(str(f))
        return groups

    def _schedule_load(self, context: QgsProcessingContext, output_path: str, layer_name: str, group_name: str):
        # Layer automatisch nach Abschluss laden
        details = QgsProcessingContext.LayerDetails(layer_name, QgsProject.instance(), group_name)
        context.addLayerToLoadOnCompletion(output_path, details)

    # ---------- Hauptlogik ----------

    def processAlgorithm(self, parameters, context: QgsProcessingContext, feedback: QgsProcessingFeedback):
        root = Path(self.parameterAsFile(parameters, self.INPUT_DIR, context))
        if not root.exists():
            raise QgsProcessingException(f"Input folder does not exist: {root}")

        recursive = self.parameterAsBoolean(parameters, self.RECURSIVE, context)
        glob_pat = self.parameterAsString(parameters, self.GLOB, context) or "*.tif"
        ignore_nodata = self.parameterAsBoolean(parameters, self.IGNORE_NODATA, context)
        out_dir = Path(self.parameterAsFileOutput(parameters, self.OUTPUT_DIR, context))
        overwrite = self.parameterAsBoolean(parameters, self.OVERWRITE, context)
        out_dir.mkdir(parents=True, exist_ok=True)

        # 1) Dateien finden
        files = list(self._iter_files(root, glob_pat, recursive))
        if not files:
            raise QgsProcessingException("No rasters found. Check folder and file filter.")

        # 2) Gruppieren nach erster Zahl
        groups = self._group_by_first_number(files)
        if not groups:
            raise QgsProcessingException("No groups could be created.")

        # 3) Pro Gruppe Zell-Maximum berechnen
        group_title = "Maximum per group (first number)"
        keys = sorted(groups.keys(), key=lambda k: int(k) if k.isdigit() else k)
        total = len(keys)
        group_outputs: list[str] = []

        for i, key in enumerate(keys, start=1):
            if feedback.isCanceled():
                break

            in_list = groups[key]
            if len(in_list) < 2:
                feedback.pushInfo(f"Group {key}: < 2 rasters – skipped.")
                feedback.setProgress(100 * i / total)
                continue

            # schöner Outputname (Zahl ohne führende Nullen, sonst unverändert)
            key_print = int(key) if key.isdigit() else key
            out_path = out_dir / f"{key_print}_max.tif"

            if out_path.exists() and not overwrite:
                feedback.pushInfo(f"Skipping existing file (overwrite = No): {out_path.name}")
                # Optional trotzdem laden:
                self._schedule_load(context, str(out_path), out_path.stem, group_title)
                feedback.setProgress(100 * i / total)
                continue

            params = {
                "INPUT": in_list,
                "STATISTIC": 7,              # 7 = Maximum
                "IGNORE_NODATA": ignore_nodata,
                "REFERENCE_LAYER": in_list[0],  # ← erstes Gruppen-Raster als Referenz
                "OUTPUT": str(out_path),
            }

            try:
                processing.run("native:cellstatistics", params, context=context, feedback=feedback)
                # self._schedule_load(context, str(out_path), out_path.stem, group_title)
                feedback.pushInfo(f"Gruppe {key} → {out_path.name}")
            except Exception as e:
                feedback.reportError(f"Error in group {key}: {e}")

            feedback.setProgress(100 * i / total)

            group_outputs.append(str(out_path))

        final_max = str(out_dir / "wind_protection.tif")
        processing.run("native:cellstatistics", {
            "INPUT": group_outputs,
            "STATISTIC":  7,  # 7 = Maximum
            "IGNORE_NODATA": True,
            "REFERENCE_LAYER": group_outputs[0],  # sicheres Grid
            "OUTPUT": final_max
        }, context=context, feedback=feedback)

        self._schedule_load(context, str(final_max), Path(final_max).stem, "Group maximum")
        #schedule_load(context, final_max, Path(final_max).stem, "Gruppen-Max")

        return {self.OUTPUT_DIR: str(out_dir)}