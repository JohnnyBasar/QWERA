# -*- coding: utf-8 -*-
"Tool 4: Susceptibility of soils to wind erosion - Mapper"

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterRasterDestination,
    QgsProcessingException,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterField,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterRasterDestination,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingException,
    QgsCoordinateReferenceSystem,
    QgsRasterLayer,
    QgsVectorLayer,
    QgsProcessingParameterFile
)
from qgis import processing
from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsVectorLayer, QgsField, edit
import os
from qgis.PyQt.QtGui import QIcon

class tool_4_susceptibility_of_soils_to_wind_erosion(QgsProcessingAlgorithm):
    INPUT_EROD = "INPUT_EROD"
    INPUT_PROTEC = "INPUT_PROTEC"
    OUTPUT_DIR = "OUTPUT_DIR"
    LOAD_OUTPUTS = "LOAD_OUTPUTS"

    def icon(self):
    # Pfad relativ zu diesem Dateiordner
        icon_path = os.path.join(os.path.dirname(__file__), "..", "icons", "qwera_tool_4.svg")
        return QIcon(icon_path)

    def name(self):
        return "tool_4_susceptibility_of_soils_to_wind_erosion"

    def displayName(self):
        return "Tool 4: Susceptibility of soils to wind erosion - Mapper"

    # def group(self):
    #     return "TOOLBOX QWERA"

    # def groupId(self):
    #     return "toolbox_qwera"

    def createInstance(self):
        return tool_4_susceptibility_of_soils_to_wind_erosion()

    def shortHelpString(self):
        return """
            <h2>Description</h2>
            <p>
            This tool calculates a raster of the <b>susceptibility of soils to wind erosion</b> by combining:
            (1) the <b>Soil Erodibility</b> raster (classes 1–5, e.g., from the <i>Soil-Erodibility-Mapper-Tool</i>) and
            (2) the <b>Wind Protection</b> raster (classes 1–5, e.g., from <i>Tool 3: Wind protection Mapper</i>).
            The combination is performed with a predefined logical expression (raster calculator) as presented by <b>Funk &amp; V&ouml;lker (2024)</b> that maps erodibility × protection classes to a final susceptibility class.
            </p>

            <h2>Standards & References</h2>
            <dt><ul>
            <li><b>DIN 19706:2013-02</b> — soil susceptibility to wind erosion; basis for the erodibility concept.</li>
            <li><b><a href="https://www.sciencedirect.com/science/article/pii/S2215016124004576">Funk &amp; V&ouml;lker (2024)</a></b>, “A GIS-toolbox for a landscape structure based Wind Erosion Risk Assessment (WERA)” — describes the methodological context of using DWD wind statistics for erosion risk modeling.</li>
            </ul></dt>

            <h2>Inputs</h2>
            <dt><ul>
            <li><b>Soil Erodibility raster (1–5)</b> — Grid corresponding to classification requirements of <b>DIN 19706:2013-02</b>.</li>
            <li><b>Wind Protection raster (1–5)</b> — output from <i>Tool 3: Wind protection Mapper</i>.</li>
            <li><b>Output</b> — target raster (TEMPORARY_OUTPUT by default).</li>
            <li><b>Load into QGIS after finishing</b> — optionally add the result to the project.</li>
            </ul></dt>

            <h2>Outputs</h2>
            <dt><ul>
            <li><b>Susceptibility raster</b> — final classes per cell according to the erodibility × protection rules.</li>
                <dd><ul style="list-style-type:square;">
                <li><i>Class 1</i> — very low</li>
                <li><i>Class 2</i> — low</li>
                <li><i>Class 3</i> — medium</li>
                <li><i>Class 4</i> — high</li>
                <li><i>Class 5</i> — very high</li>
                </ul></dd>
            </ul></dt>

            <h2>Notes</h2>
            <dt><ul>
            <li>Both inputs must share the same CRS; otherwise an error is raised.</li>
            <li>The tool attempts <code>native:rastercalc</code> and falls back to <code>qgis:rastercalculator</code> when needed.</li>
            <li>ChatGPT was used to create this plugin.</li>
            <li>Tested with QGIS 3.44.x (Python 3.12, Windows).</li>
            </ul></dt>
        """



    def initAlgorithm(self, config=None):
        # 1) Create parameter…
        p_erod = QgsProcessingParameterRasterLayer(self.INPUT_EROD, "<h4>Soil Erodibility Raster:</h4>")
        # 2) Set help…
        p_erod.setHelp("Raster layer with 5 classes. Output from the Soil-Erodibility-Mapper-Tool")
        # 3) Register
        self.addParameter(p_erod)

        p_protect = QgsProcessingParameterRasterLayer(self.INPUT_PROTEC, "<h4>Wind Protection Raster:</h4>")
        # 2) Set help…
        p_protect.setHelp("Raster layer with 5 classes. Output from Tool 3")
        # 3) Register
        self.addParameter(p_protect)


        self.addParameter(
            QgsProcessingParameterRasterDestination(
                self.OUTPUT_DIR,
                "Output",
                defaultValue="TEMPORARY_OUTPUT"
            )
        )

        self.addParameter(QgsProcessingParameterBoolean(
            self.LOAD_OUTPUTS, "Load into QGIS after finishing", defaultValue=False))


    #---------------------------------------------------------------------------------
    def processAlgorithm(self, parameters, context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):

        # Helper functions
        def ensure_crs(vl, target_crs):
            """Reproject if needed, otherwise return the layer unchanged."""
            if vl.crs() != target_crs:
                return processing.run(
                    "native:reprojectlayer",
                    {"INPUT": vl, "TARGET_CRS": target_crs, "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT},
                    context=context, feedback=feedback
                )["OUTPUT"]
            return vl

        #---------------------------------------------------------------------------------
        # Read data
        # Erodibility raster
        erod_layer = self.parameterAsRasterLayer(parameters, self.INPUT_EROD, context)
        if erod_layer is None:
            raise QgsProcessingException("Soil Erodibility raster could not be loaded.")

        # SOM vector layer
        protec_layer = self.parameterAsRasterLayer(parameters, self.INPUT_PROTEC, context)
        if protec_layer is None:
            raise QgsProcessingException("Wind protection raster could not be loaded.")

        out_dst = self.parameterAsOutputLayer(parameters, self.OUTPUT_DIR, context)
        if not out_dst:
            out_dst = QgsProcessing.TEMPORARY_OUTPUT
        #-----------------------------------------------------------------------------------


        rCRS = protec_layer.crs()
        rEXT = protec_layer.extent()
        rWIDTH = protec_layer.width()
        rHEIGHT = protec_layer.height()

        feedback.pushInfo("Step 1: Checking CRS")
        if rCRS != erod_layer.crs():
            raise QgsProcessingException("Input Rasters are NOT having the same CRS. Please fix that yourself")

        # Final erodibility map
        feedback.pushInfo("Step 2: Calculating final susceptibility of soils to wind erosion map…")

        erod = f"\"{erod_layer.name()}@1\""  # dynamic, quoted layer name
        protect = f"\"{protec_layer.name()}@1\""  # dynamic, quoted layer name

        expr = f"""
                 if({erod} = 1 AND {protect} >= 1 AND {protect} <= 5, 0,
                 if({erod} = 2 AND {protect} = 1, 1, 
                 if({erod} = 2 AND {protect} >= 2 AND {protect} <= 5, 0, 
                 if({erod} = 3 AND {protect} = 1, 2, 
                 if({erod} = 3 AND {protect} = 2, 1,
                 if({erod} = 3 AND {protect} >= 3 AND {protect} <= 5, 0,
                 if({erod} = 4 AND {protect} = 1, 3, 
                 if({erod} = 4 AND {protect} = 2, 2,
                 if({erod} = 4 AND {protect} = 3, 1, 
                 if({erod} = 4 AND {protect} >= 4 AND {protect} <= 5, 0,
                 if({erod} = 5 AND {protect} = 1, 4,
                 if({erod} = 5 AND {protect} = 2, 3,
                 if({erod} = 5 AND {protect} = 3, 2,
                 if({erod} = 5 AND {protect} = 4, 1,
                 if({erod} = 5 AND {protect} = 5, 0, 
                        {erod}
                     )))))))))))))))
                 """

        try:
            out = processing.run(
                "native:rastercalc",
                {
                    "LAYERS": [erod_layer, protec_layer],
                    "EXPRESSION": expr,
                    "EXTENT": rEXT,
                    "CRS": rCRS,
                    "OUTPUT": out_dst
                },
                context=context, feedback=feedback, is_child_algorithm=True
            )["OUTPUT"]
        except Exception as e:
            feedback.reportError(f"native:rastercalc failed: {e}; falling back to qgis:rastercalculator …")
            out = processing.run(
                "qgis:rastercalculator",
                {
                    "EXPRESSION": expr.replace(erod_layer.name(), "A").replace(protec_layer.name(), "B").replace('"', ''),
                    "LAYERS": [erod_layer, protec_layer],
                    "CRS": rCRS,
                    "EXTENT": rEXT,
                    "WIDTH": rWIDTH,
                    "HEIGHT": rHEIGHT,
                    "OUTPUT": out_dst
                },
                context=context, feedback=feedback, is_child_algorithm=True
            )["OUTPUT"]
        #------------------------------------------------------------------------------------------------
        if self.parameterAsBoolean(parameters, self.LOAD_OUTPUTS, context):
            context.addLayerToLoadOnCompletion(
                out,
                QgsProcessingContext.LayerDetails("susceptibility_of_soils_to_wind_erosion", context.project(), self.OUTPUT_DIR)
            )

        return {self.OUTPUT_DIR: out}