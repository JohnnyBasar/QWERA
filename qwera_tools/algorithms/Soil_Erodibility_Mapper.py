# -*- coding: utf-8 -*-
"""
Soil Erodibility Mapper

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

def classify(v, classifier):
    # Classification helper used when no CSV lookup is provided.
    # classifier == 1 → soil texture code groups (string) mapped to class 1–6
    # classifier == 2 → SOM percentage (numeric) mapped to class 1–4
    if classifier == 1:
        cl_one = {
            'Boden_1': ('Tt', 'Tu4', 'Tu3', 'Tu2', 'Tl', 'Ts2', 'Ts3', 'Ts4'),
            'Boden_2': ('Lts', 'Ls4', 'Ls3', 'Ls2', 'Lt2', 'Lt3', 'Lu', 'Uu', 'Ut2', 'Ut3', 'Ut4', 'Uls', 'Sl4', 'St3'),
            'Boden_3': ('Us', 'Slu', 'Sl3', 'St2'),
            'Boden_4': ('Sl2', 'Su2', 'Su3', 'Su4'),
            'Boden_5': ('mS', 'gS', 'mSgs', 'gSfs', 'gSms'),
            'Boden_6': ('fSgs', 'mSfs', 'fS', 'fSms')
        }
        if v in cl_one['Boden_1']:
            return 1
        elif v in cl_one['Boden_2']:
            return 2
        elif v in cl_one['Boden_3']:
            return 3
        elif v in cl_one['Boden_4']:
            return 4
        elif v in cl_one['Boden_5']:
            return 5
        elif v in cl_one['Boden_6']:
            return 6
        elif v is None:
            return None
        else:
            return 0

    if classifier == 2:
        if v < 1:
            return 1
        elif 1 <= v <= 15:
            return 2
        elif 15 < v < 30:
            return 3
        elif 30 <= v:
            return 4
        elif v is None:
            return None
        else:
            return 0



class tool_0_3_soil_erodibility(QgsProcessingAlgorithm):
    INPUT_DEM = "INPUT_DEM"
    INPUT_SOM = "INPUT_SOM"
    FIELD_SOM = "FIELD_SOM"
    INPUT_SOIL = "INPUT_SOIL"
    FIELD_SOIL = "FIELD_SOIL"
    OUTPUT_DIR = "OUTPUT_DIR"
    LOAD_OUTPUTS = "LOAD_OUTPUTS"
    LKP_SOIL = "LKP_SOIL"

    def icon(self):
    # Pfad relativ zu diesem Dateiordner
        icon_path = os.path.join(os.path.dirname(__file__), "..", "icons", "qwera_tool_0.svg")
        return QIcon(icon_path)

    def name(self):
        return "tool_0_3_soil_erodibility"

    def displayName(self):
        return "Soil Erodibility Mapper"

    def group(self): 
        return ("Additional Tools")
    
    def groupId(self): 
        return "additional_tools"

    def createInstance(self):
        return tool_0_3_soil_erodibility()

    def shortHelpString(self):
        return """
            <h2>Description</h2>
            <p>
            This tool creates a <b>soil erodibility map</b> by combining information on <b>soil texture/type</b> and <b>soil organic matter (SOM)</b>.
            The inputs (vector layers) are classified and rasterized onto a reference DEM grid to produce a final raster of erodibility classes.
            The specified raster is used as a template for the resolution and extent of the output grid.
            The classification will be carried out according to either an user-provided CSV lookup or an internal DIN-based rule set (<b>DIN 19706</b> ). 
            </p>

            <h2>Standards & References</h2>
            <dt><ul>
            <li><b>DIN 19706:2013-02</b> — “Soil quality – Determination of soil susceptibility to wind erosion” — defines the method and classification principles used in this tool.</li>
            <li><b><a href="https://www.sciencedirect.com/science/article/pii/S2215016124004576">Funk &amp; V&ouml;lker (2024)</a></b>, “A GIS-toolbox for a landscape structure based Wind Erosion Risk Assessment (WERA)” — methodological framework in which this tool forms the soil-erodibility component.</li>
            </ul></dt>


            <h2>Inputs</h2>
            <dt><ul>
            <li><b>Reference raster</b> — DEM or equivalent raster defining CRS, extent, and cell size.</li>
            <li><b>Soil polygons</b> — vector layer containing soil type or texture codes.</li>
            <li><b>Field with soil types</b> — attribute field storing soil texture/type codes.</li>
            <li><b>SOM polygons</b> — vector layer containing soil organic matter (SOM) content in percent.</li>
            <li><b>SOM content field</b> — attribute field storing SOM values (%).</li>
            <li><b>Lookup CSV for soil types (optional)</b> — defines a custom mapping between soil codes and erodibility classes. If omitted, the built-in DIN-based mapping is applied.</li>
            <li><b>Output raster</b> — destination for the final erodibility map (default: temporary output).</li>
            <li><b>Load into QGIS after finishing</b> — if checked, the resulting raster is automatically added to the project.</li>
            </ul></dt>

            <h2>Outputs</h2>
            <dt><ul>
            <li><b>Final erodibility raster</b> — single-band raster aligned to the DEM grid. Each pixel contains the resulting erodibility class.</li>
                <dd><ul style="list-style-type:square;">
                <li><i>Class 1</i> — very low</li>
                <li><i>Class 2</i> — low</li>
                <li><i>Class 3</i> — medium</li>
                <li><i>Class 4</i> — high</li>
                <li><i>Class 5</i> — very high</li>
                </ul></dd>
            <dt><ul>
            <li><b>NoData value</b>: -9999 (for areas outside the valid extent or missing input data).</li>
            </ul></dt>

            <h2>Notes</h2>
            <dt><ul>
            <li>Requires <i>gdal</i>, <i>qgis</i>, and <i>native</i> processing providers to be active.</li>
            <li>Lookup CSV must contain at least <code>soil_code</code> and <code>class</code> columns.</li>
            <li>All outputs share the DEM’s CRS and resolution.</li>
            <li>ChatGPT was used to create this plugin.</li>
            <li>Tested with QGIS 3.44.x (Python 3.12, Windows).</li>
            </ul></dt>
        """


    def initAlgorithm(self, config=None):
        # 1) Create parameter…
        p_dem = QgsProcessingParameterRasterLayer(self.INPUT_DEM, "<h4>Reference raster (e.g. the DEM):</h4>")
        # 2) Set help…
        p_dem.setHelp("Raster layer used as reference. Extent, CRS, and cell size will be derived from it (ideally the DEM).")
        # 3) Register
        self.addParameter(p_dem)

        p_soil = QgsProcessingParameterVectorLayer(self.INPUT_SOIL, "<h4>Polygon layer containing soil texture/type information:</h4>")
        p_soil.setHelp("Soil types as a vector layer.")
        self.addParameter(p_soil)

        p_fieldSoil = QgsProcessingParameterField(
            self.FIELD_SOIL, "Attribute field containing soil texture/type codes (string)",
            parentLayerParameterName=self.INPUT_SOIL,
            type=QgsProcessingParameterField.String,
            optional=False
        )
        self.addParameter(p_fieldSoil)

        p_som = QgsProcessingParameterVectorLayer(self.INPUT_SOM, "<h4>Polygon layer containing soil organic matter content (%):</h4>")
        p_som.setHelp("Soil organic matter (%).")
        self.addParameter(p_som)

        p_fieldSOM = QgsProcessingParameterField(
            self.FIELD_SOM, "Attribute field with SOM values (%) (numeric)",
            parentLayerParameterName=self.INPUT_SOM,
            type=QgsProcessingParameterField.Numeric,
            optional=False
        )
        self.addParameter(p_fieldSOM)

        SoilTable = QgsProcessingParameterFile(
            self.LKP_SOIL, "Optional CSV lookup table for mapping soil codes to erodibility classes",
            behavior=QgsProcessingParameterFile.File,
            fileFilter="CSV (*.csv);;Text (*.txt)",
            optional=True)
        SoilTable.setHelp("If not provided, the built-in DIN-19706-based mapping is used.")
        self.addParameter(SoilTable)

        self.addParameter(
            QgsProcessingParameterRasterDestination(
                self.OUTPUT_DIR,
                "Output raster (final erodibility map)",
                defaultValue="TEMPORARY_OUTPUT"
            )
        )

        self.addParameter(QgsProcessingParameterBoolean(
            self.LOAD_OUTPUTS, "Automatically load the result into QGIS after completion", defaultValue=False))

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

        def load_csv_table(path, sep=";"):
            uri = f'file:///{path}?type=csv&detectTypes=yes&maxFields=10000&delimiter={sep}&quote="'
            tbl = QgsVectorLayer(uri, "soil_lookup", "delimitedtext")
            if not tbl.isValid():
                raise QgsProcessingException(f"The lookup CSV could not be loaded: {path}")
            return tbl

        def rasterize_to_dem(vl, field, name):
            res = processing.run(
                "gdal:rasterize",
                {
                    "INPUT": vl,
                    "FIELD": field,
                    "UNITS": 0,  # pixels
                    "WIDTH": rWIDTH,
                    "HEIGHT": rHEIGHT,
                    "EXTENT": rEXT,
                    "NODATA": -9999,
                    "INIT": -9999,
                    "INVERT": False,
                    # "EXTRA": ("-tap " + ("-at" if all_touched else "")).strip(),  # target-aligned, optional all-touched
                    "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT
                },
                context=context, feedback=feedback, is_child_algorithm=True
            )
            rl = QgsRasterLayer(res["OUTPUT"], name)
            if not rl.isValid():
                raise QgsProcessingException(f"Rasterization output '{name}' is invalid.")
            return rl


        def check_and_fix_validity(vlayer, context, feedback, name):
            # 1) Validate geometries
            res = processing.run(
                "native:checkvalidity",
                {
                    "INPUT_LAYER": vlayer,
                    # "METHOD": 0,  # optional: choose validation engine, default is fine
                    "VALID_OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
                    "INVALID_OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
                    "ERROR_OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
                },
                context=context, feedback=feedback, is_child_algorithm=True
            )

            # valid_lyr = res["VALID_OUTPUT"]  # valid features only
            invalid_lyr = res["INVALID_OUTPUT"]  # invalid features only
            error_pts = res["ERROR_OUTPUT"]      # error points (often includes a 'message' field)

            # 2) Count invalid features
            # invalid_count = invalid_lyr.featureCount() if invalid_lyr else 0
            invalid_count = res["INVALID_COUNT"] if invalid_lyr else 0
            feedback.pushInfo(f"[{name}] invalid features: {invalid_count}")

            # 3) Optional: summarize error types (Top messages)
            if invalid_count:
                try:
                    stats = processing.run(
                        "qgis:basicstatisticsforfields",
                        {"INPUT_LAYER": error_pts, "FIELD_NAME": "message"},
                        context=context, feedback=feedback, is_child_algorithm=True
                    )["STATISTICS"]
                    feedback.pushInfo(f"[{name}] error summary: {stats.get('UNIQUE_VALUES', 'n/a')} types")
                except Exception:
                    pass  # if the error field name differs, skip quietly

            # 4) Repair only if necessary
            if invalid_count > 0:
                feedback.pushInfo(f"[{name}] fixing geometries (fixgeometries)…")
                fixed = processing.run(
                    "native:fixgeometries",
                    {"INPUT": vlayer, "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT},
                    context=context, feedback=feedback, is_child_algorithm=True
                )["OUTPUT"]

                # Optional: post-check (should be zero)
                # res2 = processing.run(
                #     "native:checkvalidity",
                #     {
                #         "INPUT_LAYER": fixed,
                #         "VALID_OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
                #         "INVALID_OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
                #         "ERROR_OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
                #     },
                #     context=context, feedback=feedback, is_child_algorithm=True
                # )
                # invalid_after = res2["INVALID_COUNT"]
                # if invalid_after > 0:
                #     feedback.reportError(f"[{name}] Warning: {invalid_after} invalid features remain after fixgeometries.")
                return fixed, invalid_lyr, error_pts  # repaired layer + diagnostics
            # 5) If all valid, return original
            return vlayer, invalid_lyr, error_pts

        #--------------------------------------------------#
        # Read data
        # Reference raster
        dem_layer =  self.parameterAsRasterLayer(parameters, self.INPUT_DEM, context)
        if dem_layer is None:
            raise QgsProcessingException("The reference raster could not be loaded.")

        # SOM vector layer
        vSOM = self.parameterAsVectorLayer(parameters, self.INPUT_SOM, context)
        if vSOM is None:
            raise QgsProcessingException("The SOM input layer is invalid.")

        # Soil vector layer
        vSoil = self.parameterAsVectorLayer(parameters, self.INPUT_SOIL, context)
        if vSoil is None:
            raise QgsProcessingException("The soil type input layer is invalid.")

        # Field names
        fld_SOM = self.parameterAsString(parameters, self.FIELD_SOM, context)
        fld_soil = self.parameterAsString(parameters, self.FIELD_SOIL, context)

        out_dst = self.parameterAsOutputLayer(parameters, self.OUTPUT_DIR, context)
        if not out_dst:
            out_dst = QgsProcessing.TEMPORARY_OUTPUT


        # ------------ Extract helper parameters ---------------------------------#

        rCRS = dem_layer.crs()
        rEXT = dem_layer.extent()
        rWIDTH = dem_layer.width()
        rHEIGHT = dem_layer.height()


        # Harmonize and prepare vectors
        feedback.pushInfo("Step 1: Preparing vector layers")
        # CRS check via helper
        vSoil_crs = ensure_crs(vSoil, rCRS)
        vSOM_crs = ensure_crs(vSOM, rCRS)

        # Geometry fix
        vSoil_fix, vSoil_invalid, vSoil_errors = check_and_fix_validity(vSoil_crs, context, feedback, "soil")

        vSOM_fix, vSOM_invalid, vSOM_errors = check_and_fix_validity(vSOM_crs, context, feedback, "SOM")

        # Build spatial index (optional but often beneficial)
        processing.run("native:createspatialindex", {
            "INPUT": vSoil_fix,
        }, context=context, feedback=feedback, is_child_algorithm=True)
        processing.run("native:createspatialindex", {
            "INPUT": vSOM_fix,
        }, context=context, feedback=feedback, is_child_algorithm=True)


        # Clip both vectors to DEM extent (CLIP=True actually cuts the geometries)
        vSoil_clip = processing.run(
            "native:extractbyextent",
            {
                "INPUT": vSoil_fix,
                "EXTENT": rEXT,
                "CLIP": True,
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT
            },
            context=context, feedback=feedback
        )["OUTPUT"]

        vSOM_clip = processing.run(
            "native:extractbyextent",
            {
                "INPUT": vSOM_fix,
                "EXTENT": rEXT,
                "CLIP": True,
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT
            },
            context=context, feedback=feedback, is_child_algorithm=True
        )["OUTPUT"]

        # ------------------------------------------------------------------------
        # Add new field with classes
        feedback.pushInfo("Step 2: Assign class attributes")

        # Optional CSV lookup for soil codes → class mapping
        lkp_path = self.parameterAsFile(parameters, self.LKP_SOIL, context)
        if lkp_path:
            feedback.pushInfo("CSV file detected – attempting to apply lookup mapping.")
            lkp_tbl = load_csv_table(lkp_path, sep=";")
            join_res = processing.run(
                "native:joinattributestable",
                {
                    "INPUT": vSoil_clip,
                    "FIELD": fld_soil,            # e.g. soil_code in polygons
                    "INPUT_2": lkp_tbl,
                    "FIELD_2": "soil_code",       # from CSV
                    "FIELDS_TO_COPY": ["class", "desc"],
                    "METHOD": 1,                  # take first match
                    "DISCARD_NONMATCHING": False,
                    "PREFIX": "lkp_" ,             # avoid collisions
                    "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT
                },
                context=context, feedback=feedback, is_child_algorithm=True
            )
            vSoil_join = join_res["OUTPUT"]

            # Create/overwrite "Erod" field from joined "lkp_class"
            vSoil_clip = processing.run(
                "native:fieldcalculator",
                {
                    "INPUT": vSoil_join,
                    "FIELD_NAME": "Erod",
                    "FIELD_TYPE": 1,  # integer
                    "FIELD_LENGTH": 1,
                    "NEW_FIELD": True,
                    "FORMULA": "to_int(\"lkp_class\")",
                    "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT
                },
                context=context, feedback=feedback, is_child_algorithm=True
            )["OUTPUT"]

        else:
            feedback.pushInfo("No CSV provided – using internal classification.")
            if vSoil_clip.fields().indexFromName("Erod") == -1:
                vSoil_clip.dataProvider().addAttributes([QgsField("Erod", QVariant.Int, len=1)])
                vSoil_clip.updateFields()

            dst_idx = vSoil_clip.fields().indexFromName("Erod")
            with edit(vSoil_clip):
                for f in vSoil_clip.getFeatures():
                    vSoil_clip.changeAttributeValue(f.id(), dst_idx, classify(f[fld_soil], 1))

        # SOM classification via field calculator (no Python loop)
        vSOM_clip = processing.run(
            "native:fieldcalculator",
            {
                "INPUT": vSOM_clip,
                "FIELD_NAME": "Erod",
                "FIELD_TYPE": 1,  # integer
                "FIELD_LENGTH": 1,
                "NEW_FIELD": True,
                "FORMULA": f"""
                    CASE
                      WHEN "{fld_SOM}" < 1 THEN 1
                      WHEN "{fld_SOM}" <= 15 THEN 2
                      WHEN "{fld_SOM}" < 30 THEN 3
                      WHEN "{fld_SOM}" >= 30 THEN 4
                      ELSE NULL
                    END
                """,
                "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT
            },
            context=context, feedback=feedback, is_child_algorithm=True
        )["OUTPUT"]

        # ------------------------------------------------------------------------

        # Rasterize both class fields to the DEM grid
        feedback.pushInfo("Step 3: Rasterizing classified vectors to DEM grid.")

        rSoil = rasterize_to_dem(vSoil_clip, "Erod", "rSoil")
        rSOM = rasterize_to_dem(vSOM_clip, "Erod", "rSOM")

        # Final erodibility map
        feedback.pushInfo("Step 4: Calculating final erodibility raster.")

        soil = f"\"{rSoil.name()}@1\""  # dynamic, quoted layer name
        soml = f"\"{rSOM.name()}@1\""   # dynamic, quoted layer name

        expr = f"""
            if({soml} = 4, 5,
                if({soil} = 1 AND {soml} = 1, 1,
                if({soil} = 2 AND {soml} = 1, 2,
                if({soil} = 3 AND {soml} = 1, 3,
                if({soil} = 4 AND {soml} = 1, 4,
                if({soil} = 5 AND {soml} = 1, 5,
                if({soil} = 6 AND {soml} = 1, 5,
                if({soil} = 1 AND {soml} = 2, 0,
                if({soil} = 2 AND {soml} = 2, 1,
                if({soil} = 3 AND {soml} = 2, 2,
                if({soil} = 4 AND {soml} = 2, 3,
                if({soil} = 5 AND {soml} = 2, 4,
                if({soil} = 6 AND {soml} = 2, 5,
                if({soil} = 1 AND {soml} = 3, 1,
                if({soil} = 2 AND {soml} = 3, 2,
                if({soil} = 3 AND {soml} = 3, 3,
                if({soil} = 4 AND {soml} = 3, 4,
                if({soil} = 5 AND {soml} = 3, 5,
                if({soil} = 6 AND {soml} = 3, 5,
                   -9999
                )))))))))))))))))))
            """

        try:
            out = processing.run(
                "native:rastercalc",
                {
                    "LAYERS": [rSoil, rSOM],
                    "EXPRESSION": expr,
                    "EXTENT": rEXT,
                    "CRS": rCRS,
                    "OUTPUT": out_dst
                },
                context=context, feedback=feedback, is_child_algorithm=True
            )["OUTPUT"]
        except Exception as e:
            feedback.reportError(f"Native raster calculator failed ({e}); switching to QGIS raster calculator.")
            out = processing.run(
                "qgis:rastercalculator",
                {
                    "EXPRESSION": expr.replace(rSoil.name(), "A").replace(rSOM.name(), "B").replace('"', ''),
                    "LAYERS": [rSoil, rSOM],
                    "CRS": rCRS,
                    "EXTENT": rEXT,
                    "WIDTH": rWIDTH,
                    "HEIGHT": rHEIGHT,
                    "OUTPUT": out_dst
                },
                context=context, feedback=feedback, is_child_algorithm=True
            )["OUTPUT"]

        if self.parameterAsBoolean(parameters, self.LOAD_OUTPUTS, context):
            context.addLayerToLoadOnCompletion(
                out,
                QgsProcessingContext.LayerDetails("Soil_Erodibility", context.project(), self.OUTPUT_DIR)
            )

        return {self.OUTPUT_DIR: out}
