# -*- coding: utf-8 -*-
"""
Tool 5 – Field Blocks: Share of High-Risk Area
"""

from qgis.core import (
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer, QgsProcessingParameterNumber,
    QgsProcessingParameterFeatureSink, QgsFeatureSink, QgsFeature, QgsFields,
    QgsField, QgsWkbTypes, QgsCoordinateTransform, QgsCoordinateReferenceSystem,
    QgsProcessingContext, QgsProcessingFeedback, QgsVectorLayer, QgsRasterLayer
)
from qgis.PyQt.QtCore import QVariant
from qgis import processing
from qgis.PyQt.QtGui import QIcon
import os

class TOOLBOX_5_FeldbloeckeRiskShare(QgsProcessingAlgorithm):
    INPUT_RASTER = "INPUT_RASTER"
    INPUT_BLOCKS = "INPUT_BLOCKS"
    THRESHOLD = "THRESHOLD"
    OUTPUT = "OUTPUT"

    def icon(self):
    # Pfad relativ zu diesem Dateiordner
        icon_path = os.path.join(os.path.dirname(__file__), "..", "icons", "qwera_tool_5.svg")
        return QIcon(icon_path)
    
    def createInstance(self):
        return TOOLBOX_5_FeldbloeckeRiskShare()
    
    def name(self):
        return "tool5_feldbloecke_riskshare"

    def displayName(self):
        return "Tool 5: Field Blocks Statistics"

    # def group(self):
    #     return "QWERA – Winderosion"

    # def groupId(self):
    #     return "qwera_winderosion"

    def shortHelpString(self):
        return """
            <h2>Description</h2>
            <p>
            The tool calculates the area fraction within a polygon (e.g., field block polygon, but any structure polygon layer is fine) above a selectable threshold value based on a wind-erosion risk raster (from <i>Tool 4: Susceptibility of soils to wind erosion - Mapper</i>). It determines the proportion of each polygon’s surface where raster values are greater than or equal to a user-defined threshold (e.g., ≥ 5). The threshold refers to the risk classes according to the erodibility × protection rules:

            Results are written to a new polygon layer with additional statistical fields.
            </p>

            <h2>Standards & References</h2>
            <dt><ul>
            <li><b>DIN 19706:2013-02</b> — Soil susceptibility to wind erosion; defines the underlying risk-scale concept.</li>
            <li><b><a href="https://www.sciencedirect.com/science/article/pii/S2215016124004576">Funk &amp; V&ouml;lker (2024)</a></b>, “A GIS-toolbox for a landscape structure based Wind Erosion Risk Assessment (WERA)” — describes the methodological context of using DWD wind statistics for erosion risk modelling.</li>
            </ul></dt>


            <h2>Inputs</h2>
            <dt><ul>
            <li><b>Wind-erosion risk raster</b> — output from Tool 4 (single band, numeric scale or class values).</li>
            <li><b>Field blocks (polygon layer)</b> — vector features defining analysis units.</li>
            <li><b>Threshold</b> — numeric limit from which raster cells are included into the calculation.</li>
                <dd><ul style="list-style-type:square;">
                <li><i>Class 1</i> — very low</li>
                <li><i>Class 2</i> — low</li>
                <li><i>Class 3</i> — medium</li>
                <li><i>Class 4</i> — high</li>
                <li><i>Class 5</i> — very high</li>
                </ul></dd>
            <dt><ul>
            <li><b>Output</b> — Directory and name for the resulting polygon layer.</li>
            </ul></dt>

            <h2>Outputs</h2>
            <dt><ul>
            <li><b>Enhanced field-block layer</b> with additional attributes: </li>
                <dd><ul style="list-style-type:square;">
                <li><i>risk_count</i> — number of evaluated raster cells</li>
                <li><i>risk_sum</i> — count of cells classified as by threshold value</li>
                <li><i>area_m2</i> — total polygon area (m²)</li>
                <li><i>area_high_m2</i> — area over threshold (m²)</li>
                <li><i>pct_high</i> — percentage of threshold area</li>
                <li><i>thr_val</i> — threshold used</li>
                </ul></dd>
            <dt><ul>
            </ul></dt>

            <h2>Notes</h2>
            <dt><ul>
            <li>All geometry and area calculations are performed in the raster’s CRS (for true metric area in m²).</li>
            <li>Field blocks are reprojected automatically to the raster CRS if required.</li>
            <li>Geometries are checked and repaired when necessary (<code>native:checkvalidity</code> / <code>native:fixgeometries</code>).</li>
            <li>ChatGPT was used to create this plugin.</li>
            <li>Requires QGIS 3.44 + (Python 3.12). Tested on Windows.</li>
            </ul></dt>
        """

    

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.INPUT_RASTER,
                "Wind-erosion risk raster (from Tool 4)"
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.INPUT_BLOCKS,
                "Field blocks (or any structure polygon layer)",
                #types=[QgsProcessing.TypeVectorPolygon]
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.THRESHOLD,
                "Threshold (cells with value ≥ threshold are considered)",
                type=QgsProcessingParameterNumber.Double,
                defaultValue=5.0
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT,
                "Field blocks with threshold share (Shapefile)"
            )
        )

    def processAlgorithm(self, params, context: QgsProcessingContext, feedback: QgsProcessingFeedback):
        
        #Helpersfunctions
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
        
        risk_rlayer: QgsRasterLayer = self.parameterAsRasterLayer(params, self.INPUT_RASTER, context)
        #poly_vlayer: QgsVectorLayer = self.parameterAsVectorLayer(params, self.INPUT_BLOCKS, context)
        poly_vlayer = self.parameterAsVectorLayer(params, self.INPUT_BLOCKS, context)
        threshold: float = self.parameterAsDouble(params, self.THRESHOLD, context)

        if risk_rlayer is None or not risk_rlayer.isValid():
            raise QgsProcessingException("Input raster is invalid.")
        if poly_vlayer is None or not poly_vlayer.isValid():
            raise QgsProcessingException("Field-block layer is invalid.")

        # 1) Arbeits-CRS = Raster-CRS (für korrekte m²-Flächen)
        raster_crs = risk_rlayer.crs()
        if poly_vlayer.crs() != raster_crs:
            feedback.pushInfo("Reprojecting field blocks to raster CRS …")
            reproj = processing.run(
                "native:reprojectlayer",
                {
                    "INPUT": poly_vlayer,
                    "TARGET_CRS": raster_crs,
                    "OPERATION": "",
                    "OUTPUT": "TEMPORARY_OUTPUT",
                },
                context=context,
                feedback=feedback,
            )
            poly_proj = reproj["OUTPUT"]
        else:
            poly_proj = poly_vlayer

        feedback.pushInfo("Fixing geometry")

        poly_proj, vSoil_invalid, vSoil_errors = check_and_fix_validity(poly_proj, context, feedback, "blocks")
        feedback.pushInfo("Geometry fixed")


        # 2) Binäre Maske: 1 wenn Risiko ≥ Grenzwert, sonst 0
        feedback.pushInfo("Creating treshold mask (raster calculator) …")
            # 2) Binäre Maske: 1 wenn Risiko ≥ Grenzwert, sonst 0 (QGIS-native)
        
        layer = f"\"{risk_rlayer.name()}@1\""  # dynamic, quoted layer name
        expr = f"""{layer} >= {threshold} * 1"""

        calc = processing.run(
            "native:rastercalc",
            {
                "EXPRESSION": expr,
                "LAYERS": [risk_rlayer],
                "CRS": risk_rlayer.crs(),                 # sichert m- bzw. m²-Bezug
                "EXTENT": risk_rlayer.extent(),           # exakt Raster-Extent
                "OUTPUT": "TEMPORARY_OUTPUT",
                # Optional (nur wenn du explizit setzen willst):
                # "NODATA": 0,
                # "OUTPUT_FORMAT": 1,  # GeoTIFF
            },
            context=context,
            feedback=feedback,
        )
        mask_rlayer = QgsRasterLayer(calc["OUTPUT"], "highrisk_mask")
        if not mask_rlayer.isValid():
            raise QgsProcessingException("Mask (native) could not be created.")


        # 3) Zonal Statistics über die Maske (Summe = Anzahl 1er-Zellen, Count = Anzahl Pixel)
        feedback.pushInfo("Computing zonal statistics (sum/count) …")
        # Ab QGIS 3.44 ist 'native:zonalstatisticsfb' die schnelle Variante
        zonal = processing.run(
            "native:zonalstatisticsfb",
            {
                "INPUT": poly_proj,
                "INPUT_RASTER": mask_rlayer,
                "RASTER_BAND": 1,
                "COLUMN_PREFIX": "risk_",
                "STATISTICS": [0, 1],  # 0=Count, 2=Sum
                "OUTPUT":"TEMPORARY_OUTPUT"
            },
            context=context,
            feedback=feedback,
        )
        poly_with_stats = zonal["OUTPUT"]

        # 4) Felder für Fläche & Anteil ergänzen
        feedback.pushInfo("Calculating areas and shares …")
        dp = poly_with_stats.dataProvider()
        # Zusätzliche Felder
        add_fields = [
            QgsField("area_m2", QVariant.Double),
            QgsField("area_high_m2", QVariant.Double),
            QgsField("pct_high", QVariant.Double),
            QgsField("thr_val", QVariant.Double),
        ]
        dp.addAttributes(add_fields)
        poly_with_stats.updateFields()

        # Pixelgröße → Pixel-Fläche
        rdp = risk_rlayer.dataProvider()
        pxw = abs(risk_rlayer.rasterUnitsPerPixelX())
        pxh = abs(risk_rlayer.rasterUnitsPerPixelY())
        pixel_area = pxw * pxh

        # Feldindizes
        idx_count = poly_with_stats.fields().indexOf("risk_count")
        idx_sum = poly_with_stats.fields().indexOf("risk_sum")
        idx_area = poly_with_stats.fields().indexOf("area_m2")
        idx_high = poly_with_stats.fields().indexOf("area_high_m2")
        idx_pct = poly_with_stats.fields().indexOf("pct_high")
        idx_thr = poly_with_stats.fields().indexOf("thr_val")

        changes = {}
        for f in poly_with_stats.getFeatures():
            geom = f.geometry()
            total_area = geom.area() if geom is not None else 0.0
            sum_high = f[idx_sum] if idx_sum != -1 and f[idx_sum] is not None else 0.0
            # Summe der 1er-Zellen × Pixel-Fläche = Hochrisiko-Fläche
            area_high = float(sum_high) * pixel_area if total_area > 0 else 0.0
            pct = (area_high / total_area * 100.0) if total_area > 0 else 0.0

            changes[f.id()] = {
                idx_area: float(total_area),
                idx_high: float(area_high),
                idx_pct: float(pct),
                idx_thr: float(threshold),
            }

        if changes:
            dp.changeAttributeValues(changes)

        # 5) In Ziel-Sink schreiben (Shapefile)
        fields_out: QgsFields = poly_with_stats.fields()
        (sink, dest_id) = self.parameterAsSink(
            params, self.OUTPUT, context, fields_out, poly_with_stats.wkbType(), poly_with_stats.crs()
        )
        for f in poly_with_stats.getFeatures():
            sink.addFeature(f, QgsFeatureSink.FastInsert)

        feedback.pushInfo("Done. Fields: risk_count, risk_sum, area_m2, area_high_m2, pct_high, thr_val")
        return {self.OUTPUT: dest_id}