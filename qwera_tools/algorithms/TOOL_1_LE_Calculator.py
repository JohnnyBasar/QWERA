# -*- coding: utf-8 -*-
"""
Tool 1: Landscape Elements Calculator

"""
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterRasterDestination,
    QgsProcessingException,
    QgsProcessingParameterDefinition,
)
from qgis import processing
import os

class TOOLBOX_1(QgsProcessingAlgorithm):
    INPUT_DEM = "INPUT_DEM"
    INPUT_DOM = "INPUT_DOM"
    INPUT_VECTOR = "INPUT_VECTOR"       # optional
    OUTPUT_RASTER = "OUTPUT_RASTER"
    
    def icon(self):
    # Pfad relativ zu diesem Dateiordner
        icon_path = os.path.join(os.path.dirname(__file__), "..", "icons", "qwera_tool_1.svg")
        return QIcon(icon_path)

    def tr(self, string):
        """
        Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)
    
    def name(self):
        return "tool_1_dom_minus_dgm"

    def displayName(self):
        return "Tool 1: Landscape Elements Calculator"

    # def group(self):
    #     return "TOOLBOX QWERA"

    # def groupId(self):
    #     return "toolbox_qwera"

    def createInstance(self):
        return TOOLBOX_1()
    
    
    def shortHelpString(self):
        return """
            <h2>Description</h2>
            <p>
            This tool calculates the height difference <b>DSM − DEM</b> (Digital Surface Model minus Digital Elevation Model). Optionally, all cells located inside polygons of a given vector layer (e.g., field blocks) can be set to zero. 
            Polygon layers are reprojected (warped) to the DGM’s CRS if needed. Bilinear Method is used for the raster transformation. To avoid interpolation artefacts and to have more control it might be an advantage to align the raster inputs in advance.
            The generated grid contains the real heights of the landscape elements. The result is written to the defined output raster and automatically loaded into QGIS.
            </p>

            <h2>Standards & References</h2>
            <dt><ul>
            <li><b>GDAL Raster Calculator</b> — used for computing the difference (DOM − DGM) and applying polygon masks.</li>
            <li><b><a href="https://www.sciencedirect.com/science/article/pii/S2215016124004576">Funk &amp; V&ouml;lker (2024)</a></b>, “A GIS-toolbox for a landscape structure based Wind Erosion Risk Assessment (WERA)” — describes the methodological context of using DWD wind statistics for erosion risk modelling.</li>
            </ul></dt>

            <h2>Inputs</h2>
            <dt><ul>
            <li><b>DEM (reference grid)</b> — raster layer defining CRS, extent, and cell size.</li>
            <li><b>DSM (surface model)</b> — raster layer to be subtracted from the DGM; should match grid alignment. Otherwise, it will be warped.</li>
            <li><b>Field blocks (optional)</b> — polygon layer; all covered cells are set to zero in the output raster.</li>
            </ul></dt>

            <h2>Outputs</h2>
            <dt><ul>
            <li><b>Output LE_Raster</b> — Float32 raster representing landscape elements heights. Values inside optional field-block polygons are 0.</li>
            <li><b>Automatic loading</b> — the output raster is automatically added to the QGIS project when processing completes.</li>
            </ul></dt>

            <h2>Notes</h2>
            <dt><ul>
            <li>NoData values are preserved in both inputs during subtraction.</li>
            <li>ChatGPT was used to create this plugin.</li>
            <li>Tested with QGIS 3.44.x (Python 3.12, Windows).</li>
            </ul></dt>
        """


    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.INPUT_DEM,
                "DEM (reference grid)"
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.INPUT_DOM,
                "DSM (aligned to DEM grid)"
            )
        )

        # Optionaler Vektorlayer
        p_vec = QgsProcessingParameterVectorLayer(
            self.INPUT_VECTOR,
            "Polygon layer of field blocks (set cells within polygons to 0)",
            [QgsProcessing.TypeVectorPolygon]
        )
        p_vec.setFlags(p_vec.flags() | QgsProcessingParameterDefinition.FlagOptional)
        self.addParameter(p_vec)

        # Output: TEMPORARY_OUTPUT als Default sorgt für automatisches Laden
        self.addParameter(
            QgsProcessingParameterRasterDestination(
                self.OUTPUT_RASTER,
                "Output LE_Raster",
                defaultValue="TEMPORARY_OUTPUT"
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        # Eingaben
        dgm = self.parameterAsRasterLayer(parameters, self.INPUT_DEM, context)
        dom = self.parameterAsRasterLayer(parameters, self.INPUT_DOM, context)
        feldblock = self.parameterAsVectorLayer(parameters, self.INPUT_VECTOR, context)  # kann None sein

        if dgm is None or dom is None:
            raise QgsProcessingException("Input rasters could not be read.")

        dgm_crs = dgm.crs()
        px = dgm.rasterUnitsPerPixelX()
        py = dgm.rasterUnitsPerPixelY()
        if abs(px - py) > 1e-9:
            feedback.pushWarning(f"Non-square pixels detected in DGM (px={px}, py={py}). Result will be written as Float32.")
        
        # 1) optional, deaktiviert: DOM auf DGM-Grid bringen (gdal:warpreproject), Wenn aktiviret im calc-Teil richtige Inputparameter setzten
        if dgm_crs != dom.crs():
            feedback.pushInfo("CRS not the same. Warping")
        # RESAMPLING: 1 = Bilinear (für Höhenmodelle sinnvoll)
        # DATA_TYPE: 5 = Float32
            warp_params = {
                "INPUT": dom.source(),
                "SOURCE_CRS": dom.crs(),    # robust, auch wenn DOM ein anderes CRS hat
                "TARGET_CRS": dgm_crs,
                "RESAMPLING": 1,
                "NODATA": None,
                "TARGET_RESOLUTION": px,
                "TARGET_EXTENT": dgm.extent(),
                "TARGET_EXTENT_CRS": dgm_crs,
                "MULTITHREADING": True,
                "DATA_TYPE": 5,
                "OUTPUT": "TEMPORARY_OUTPUT",
            }
            dom = processing.run(
                "gdal:warpreproject", warp_params, context=context, feedback=feedback, is_child_algorithm=True
            )["OUTPUT"]
        else:
            feedback.pushInfo("CRS the same")
            dom = dom.source()


        # 1) Differenz berechnen (DOM - DGM)
        diff = processing.run(
            "gdal:rastercalculator",
            {
                #"INPUT_A": dom_on_dgm,   # diesen Teil wieder aktivieren wenn die warp-Funktion aktiviert ist  
                "INPUT_A": dom,  # den Teil auskommentieren wenn die Warp-Funktion aktiviert ist
                "BAND_A": 1,
                "INPUT_B": dgm.source(),
                "BAND_B": 1,
                "INPUT_C": None, "BAND_C": -1,
                "INPUT_D": None, "BAND_D": -1,
                "INPUT_E": None, "BAND_E": -1,
                "INPUT_F": None, "BAND_F": -1,
                "FORMULA": "A-B",
                "NO_DATA": None,
                "RTYPE": 5,       # Float32
                "EXTRA": "",
                "OPTIONS": "",
                "OUTPUT": "TEMPORARY_OUTPUT",
            },
            context=context,
            feedback=feedback,
            is_child_algorithm=True
        )
        diff_raster = diff["OUTPUT"]

        # --- 2) OPTIONAL: Feldblöcke auf 0 brennen ---
        if feldblock is not None:
            vec_for_rasterize = feldblock
            if feldblock.crs() != dgm_crs:
                reproj = processing.run(
                    "native:reprojectlayer",
                    {
                        "INPUT": feldblock,
                        "TARGET_CRS": dgm_crs,
                        "OPERATION": "",
                        "OUTPUT": "TEMPORARY_OUTPUT",
                    },
                    context=context,
                    feedback=feedback,
                    is_child_algorithm=True
                )
                vec_for_rasterize = reproj["OUTPUT"]

            # Brennt IN-PLACE in diff_raster
            processing.run(
                "gdal:rasterize_over_fixed_value",
                {
                    "INPUT": vec_for_rasterize,
                    "INPUT_RASTER": diff_raster,
                    "BURN": 0,
                    "ADD": False,
                    "EXTRA": None
                },
                context=context,
                feedback=feedback,
                is_child_algorithm=True
            )

            # WICHTIG: jetzt das (modifizierte) diff_raster ins finale OUTPUT schreiben,
            # damit QGIS es automatisch lädt
            saved = processing.run(
                "gdal:translate",
                {
                    "INPUT": diff_raster,
                    "TARGET_CRS": None,
                    "NODATA": None,
                    "COPY_SUBDATASETS": False,
                    "OPTIONS": "",
                    "EXTRA": "",
                    "OUTPUT": parameters[self.OUTPUT_RASTER],
                },
                context=context,
                feedback=feedback,
                is_child_algorithm=True
            )
            return {self.OUTPUT_RASTER: saved["OUTPUT"]}


        # 3) KEIN Vektorlayer: diff_raster auf finales OUTPUT schreiben (=> Auto-Laden)
        saved = processing.run(
            "gdal:translate",
            {
                "INPUT": diff_raster,
                "TARGET_CRS": None,
                "NODATA": None,
                "COPY_SUBDATASETS": False,
                "OPTIONS": "",
                "EXTRA": "",
                "OUTPUT": parameters[self.OUTPUT_RASTER],  # << finales Ziel
            },
            context=context,
            feedback=feedback,
            is_child_algorithm=True
        )
        return {self.OUTPUT_RASTER: saved["OUTPUT"]}