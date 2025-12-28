# -*- coding: utf-8 -*-
"""
ADF-zu-TIFF Stapelkonverter
- Durchsucht einen Eingabeordner rekursiv nach Arc/Info GRID-Dateien (w001001.adf)
- Leitet den Ausgabedateinamen aus dem Ordnernamen des GRIDs ab (optional Präfix entfernen)
- Schreibt GeoTIFFs (LZW, Tiled, BigTIFF bei Bedarf)
Getestet mit QGIS 3.44.x
"""

import os
import re
from pathlib import Path
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFile,
    QgsProcessingParameterString,
    QgsProcessingParameterBoolean,
    QgsProcessingMultiStepFeedback,
    QgsProcessingException,
)
from qgis import processing

class ADF2TIFF_Batch(QgsProcessingAlgorithm):
    INPUT_DIR = "INPUT_DIR"
    OUTPUT_DIR = "OUTPUT_DIR"
    STRIP_PREFIX = "STRIP_PREFIX"
    OVERWRITE = "OVERWRITE"
    ADD_TO_CANVAS = "ADD_TO_CANVAS"

    def icon(self):
    # Pfad relativ zu diesem Dateiordner
        icon_path = os.path.join(os.path.dirname(__file__), "..", "icons", "qwera_tool_0.svg")
        return QIcon(icon_path)

    def name(self):
        return "adf_to_tiff"

    def displayName(self):
        return "ADF to GeoTIFF"

    def group(self): 
        return ("Additional Tools")
    
    def groupId(self): 
        return "additional_tools"

    def shortHelpString(self):
        return """
            <p>
            This tool batch-converts <b>ArcGIS/Info GRID</b> datasets (<code>w001001.adf</code>) into tiled, LZW-compressed <b>GeoTIFF</b> files.
            It scans an input folder <b>recursively</b>, derives each output name from the GRID’s parent folder name (with an optional prefix stripped), and writes efficient TIFFs (uses <code>BigTIFF</code> automatically when needed).
            The tool was originally developed to create a bridge between the WERA Toolbox for ArcGIS and the QWERA Toolbox. It can be used after Tool 2 of the WERA Toolbox to enable the use of Tool 3 of the QWERA Toolbox.
            </p>

            <h2>Standards & References</h2>
            <dt><ul>
            <li><b>GDAL / gdal:translate</b> — used for robust conversion from Arc/Info GRID (ADF) to GeoTIFF.</li>
            <li><b>GeoTIFF</b> — output format with <i>LZW compression</i> and <i>tiling</i> enabled by default.</li>
            </ul></dt>

            <h2>Workflow</h2>
            <dt><ul>
            <li><b>Recursive scan</b>: Finds all files named <code>w001001.adf</code> anywhere under the input directory.</li>
            <li><b>Output naming</b>: The GeoTIFF name is taken from the GRID’s folder name; optional removal of a leading prefix (e.g., <code>v_</code>).</li>
            <li><b>Conversion</b>: Uses <code>gdal:translate</code> with <code>COMPRESS=LZW</code>, <code>TILED=YES</code>, <code>BIGTIFF=IF_SAFER</code>.</li>
            <li><b>Overwrite control</b>: Existing TIFFs are skipped unless overwrite is enabled.</li>
            <li><b>Optional add to map</b>: Successfully converted rasters can be added to the current QGIS project.</li>
            </ul></dt>

            <h2>Inputs</h2>
            <dt><ul>
            <li><b>Input folder (recursive)</b> — root directory containing Arc/Info GRID datasets.</li>
            <li><b>Output folder</b> — destination directory for GeoTIFFs.</li>
            <li><b>Strip prefix</b> — optional prefix to remove from the GRID folder name (leave empty to disable).</li>
            <li><b>Overwrite existing</b> — replace existing TIFF outputs if they already exist.</li>
            <li><b>Add results to map</b> — load each created TIFF into the current QGIS project.</li>
            </ul></dt>

            <h2>Outputs</h2>
            <dt><ul>
            <li><b>GeoTIFF files</b> — one per GRID dataset, LZW-compressed, tiled; BigTIFF is used automatically if file size requires it.</li>
            </ul></dt>

            <h2>Notes</h2>
            <dt><ul>
            <li>No reprojection is performed (source CRS is preserved).</li>
            <li>File names are sanitized to avoid invalid characters.</li>
            <li>Arc/Info GRID structures are detected by the presence of <code>w001001.adf</code> files.</li>
            <li>ChatGPT was used to create this plugin.</li>
            <li>Tested with QGIS 3.44.x (Windows).</li>
            </ul></dt>
        """


    def createInstance(self):
        return ADF2TIFF_Batch()
        
    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_DIR,
                "Input folder (search recursively)",
                behavior=QgsProcessingParameterFile.Folder
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(
                self.OUTPUT_DIR,
                "Output folder",
                behavior=QgsProcessingParameterFile.Folder
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.STRIP_PREFIX,
                "Strip optional prefix from folder name (leave empty to keep names)",
                defaultValue="v_",
                multiLine=False,
                optional=True
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.OVERWRITE,
                "Overwrite existing TIFFs",
                defaultValue=False
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.ADD_TO_CANVAS,
                "Add results to map",
                defaultValue=False
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        in_dir = Path(self.parameterAsFile(parameters, self.INPUT_DIR, context))
        out_dir = Path(self.parameterAsFile(parameters, self.OUTPUT_DIR, context))
        strip_prefix = self.parameterAsString(parameters, self.STRIP_PREFIX, context) or ""
        overwrite = self.parameterAsBoolean(parameters, self.OVERWRITE, context)
        add_to_canvas = self.parameterAsBoolean(parameters, self.ADD_TO_CANVAS, context)

        if not in_dir.is_dir():
            raise QgsProcessingException(f"Input folder not found: {in_dir}")
        if not out_dir.exists():
            out_dir.mkdir(parents=True, exist_ok=True)

        # Alle Treffer sammeln
        adf_files = []
        for root, dirs, files in os.walk(in_dir):
            for fn in files:
                if fn.lower() == "w001001.adf":
                    adf_files.append(Path(root) / fn)

        if not adf_files:
            feedback.pushWarning("No w001001.adf files found.")
            return {}

        feedback.pushInfo(f"{len(adf_files)} GRID(s) found.")

        ms_feedback = QgsProcessingMultiStepFeedback(len(adf_files), feedback)

        for i, adf_path in enumerate(adf_files):
            if ms_feedback.isCanceled():
                break

            grid_dir = Path(adf_path).parent
            base_name = grid_dir.name  # entspricht dirname(files[i]) |> basename() in R

            if strip_prefix and base_name.startswith(strip_prefix):
                base_name = base_name[len(strip_prefix):]

            # Sauberer Dateiname (nur zur Sicherheit)
            base_name = re.sub(r"[^\w\-\.]+", "_", base_name)

            out_tif = out_dir / f"{base_name}.tif"

            if out_tif.exists() and not overwrite:
                ms_feedback.pushInfo(f"Skipping (already exists): {out_tif}")
                ms_feedback.setCurrentStep(i + 1)
                ms_feedback.setProgress((i + 1) / len(adf_files) * 100)
                continue

            ms_feedback.pushInfo(f"Converting: {adf_path} → {out_tif}")

            # GDAL Translate via Processing (bewährt & mit COG-/Tiling-/Kompressionsoptionen)
            # Hinweis: GDAL kann w001001.adf direkt öffnen; alternativ könnte man grid_dir angeben.
            params = {
                "INPUT": str(adf_path),
                "TARGET_CRS": None,  # CRS unverändert
                "NODATA": None,
                "COPY_SUBDATASETS": False,
                "OPTIONS": "",
                "EXTRA": "",
                "DATA_TYPE": 0,  # original
                "OUTPUT": str(out_tif),
                "CREATEOPTIONS": [
                    "COMPRESS=LZW",
                    "TILED=YES",
                    "BIGTIFF=IF_SAFER"
                ]
            }

            processing.run(
                "gdal:translate",
                params,
                context=context,
                feedback=ms_feedback,
                is_child_algorithm=True
            )

            if add_to_canvas:
                # Ausgabe in das Projekt laden
                try:
                    context.addLayerToLoadOnCompletion(
                        str(out_tif),
                        QgsProcessing.LayerDetails(
                            name=base_name,
                            project=context.project()
                        )
                    )
                except Exception as e:
                    ms_feedback.pushWarning(f"Could not load layer: {e}")

            ms_feedback.setCurrentStep(i + 1)
            ms_feedback.setProgress((i + 1) / len(adf_files) * 100)

        return {}


# Registrierung für den Processing-Skripteditor:
def classFactory():
    return ADF2TIFF_Batch()
