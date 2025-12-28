# -*- coding: utf-8 -*-
"""
DWD – Stations-Finder (Wind), wetterdienst-frei

Nutzt dwd_cdc.py, um Stationsmetadaten direkt vom DWD-CDC zu laden.
Unterstützt:
- Name-Filter
- Extent-Filter (Projekt-CRS -> WGS84)
- Zeitfilter (Start/Ende)
- Ausgabe im wählbaren Ziel-CRS
"""
import os
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsProcessing, QgsProcessingAlgorithm,
    QgsProcessingParameterEnum, QgsProcessingParameterString,
    QgsProcessingParameterDateTime, QgsProcessingParameterExtent,
    QgsProcessingParameterCrs, QgsProcessingParameterFeatureSink,
    QgsProcessingException, QgsProcessingParameterDefinition,
    QgsFields, QgsField, QgsFeature, QgsGeometry, QgsPointXY,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsWkbTypes,
)
from qgis.utils import QgsMessageLog

try:
    from . import dwd_cdc  # Plugin-Kontext
except Exception:  # pragma: no cover
    import dwd_cdc         # Standalone-Test


class DwdStationFinder(QgsProcessingAlgorithm):

    P_SEARCH = "P_SEARCH"
    P_EXTENT = "P_EXTENT"
    P_START = "P_START"
    P_END = "P_END"
    P_RESOLUTION = "P_RESOLUTION"
    P_WIND_MODE = "P_WIND_MODE"
    P_CRS = "P_CRS"
    P_SINK = "P_SINK"

    RES_OPTIONS = [
        "10-minute (minute_10)",
        "Hourly (hourly)",
        "Daily (not yet supported)",
        "Monthly (not yet supported)",
    ]
    RES_MAP = {0: "minute_10", 1: "hourly", 2: "daily", 3: "monthly"}

    WIND_MODE_OPTIONS = [
        "Wind speed (mean wind)",
        "Maximum wind (gusts)",
    ]
    WIND_MODE_MAP = {
        0: "wind_speed",
        1: "wind_gust_max",
    }

    # ------------------------------------------------------------------
    # Boilerplate
    # ------------------------------------------------------------------
    
    def icon(self):
        icon_path = os.path.join(os.path.dirname(__file__), "..", "icons", "qwera_tool_0.svg")
        return QIcon(icon_path)
    
    def name(self):
        return "dwd_station_finder"

    def displayName(self):
        return self.tr("DWD Station Finder (Wind)")

    def group(self):
        return "Additional Tools"

    def groupId(self):
        return "additional_tools"

    def createInstance(self):
        return DwdStationFinder()

    def tr(self, string):
        return QCoreApplication.translate("DwdStationFinder", string)

    def shortHelpString(self):
        return """
            <p>
            This tool queries and lists <b>Deutscher Wetterdienst (DWD)</b> weather stations providing <b>wind data</b> of a choosable temporal resolution (wind speed and wind direction). 
            Users can search by <b>station name</b> and/or <b>map extent</b>, optionally restricted by date range. 
            Results are returned as a point layer with full station metadata.
            </p>

            <h2>Standards & References</h2>
            <dt><ul>
            <li><b><a href="https://www.dwd.de/EN/Home/home_node.html">Deutscher Wetterdienst (DWD) Open Data</a></b> — official meteorological observation source.</li>
            <li><b><a href="https://pypi.org/project/wetterdienst/">Wetterdienst Python package</a></b> — provides API access to DWD observation metadata and data.</li>
            <li><b><a href="https://www.sciencedirect.com/science/article/pii/S2215016124004576">Funk &amp; V&ouml;lker (2024)</a></b>, “A GIS-toolbox for a landscape structure based Wind Erosion Risk Assessment (WERA)” — outlines the scientific context for integrating DWD stations in wind-erosion modeling.</li>
            </ul></dt>

            <h2>Inputs</h2>
            <dt><ul>
            <li><b>Station name contains (optional)</b> — partial text to match DWD station names.</li>
            <li><b>Filter by map extent (optional)</b> — limits search to visible map area or defined bounding box.</li>
            <li><b>Temporal resolution</b> — 10-minute, hourly, daily, or monthly datasets available from DWD.</li>      
            <li><b>Wind mode</b> — Either “mean wind speed” or “maximum wind gust” can be selected. If “maximum wind gust” has been selected it overwrites the Temporal resolution since wind gust data is only available for the 10-minute resolution.</li>
            <li><b>Start date (UTC, optional)</b> — earliest date for active stations.</li>
            <li><b>End date (UTC, optional)</b> — latest date for active stations.</li>
            <li><b>Target CRS</b> — coordinate reference system for output points.</li>
            <li><b>Output (point layer)</b> — resulting vector layer with station locations and metadata.</li>
            </ul></dt>

            <h2>Outputs</h2>
            <dt><ul>
            <li><b>Station layer</b> — points representing DWD wind stations, each with:
                <dd><ul style="list-style-type:square;">
                <li>station_id, name, state</li>
                <li>height_m (station elevation)</li>
                <li>latitude / longitude (WGS84)</li>
                <li>from_date / to_date (period of record)</li>
                </ul></dd>
            </li>
            </ul></dt>

            <h2>Notes</h2>
            <dt><ul>
            <li>Either a station name or an extent must be provided; both can also be combined.</li>
            <li>Requires internet access.</li>
            <li>“Hourly wind” dataset corresponds to DWD observation category <code>("hourly", "wind")</code>.</li>
            <li>ChatGPT was used to create this plugin.</li>
            <li>Tested with QGIS 3.44.x (Python 3.12, Windows).</li>
            </ul></dt>
        """

    # ------------------------------------------------------------------
    # Parameterdefinition
    # ------------------------------------------------------------------
    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterString(
                self.P_SEARCH,
                self.tr("Station name contains (optional)"),
                defaultValue="",
                optional=True,
            )
        )

        extent_param = QgsProcessingParameterExtent(
            self.P_EXTENT,
            self.tr("Filter by map extent (optional)"),
            optional=True,
        )
        self.addParameter(extent_param)

        start_param = QgsProcessingParameterDateTime(
            self.P_START,
            self.tr("Start date (optional)"),
            type=QgsProcessingParameterDateTime.DateTime,
            optional=True,
        )
        self.addParameter(start_param)

        end_param = QgsProcessingParameterDateTime(
            self.P_END,
            self.tr("End date (optional)"),
            type=QgsProcessingParameterDateTime.DateTime,
            optional=True,
        )
        self.addParameter(end_param)

        self.addParameter(
            QgsProcessingParameterEnum(
                self.P_RESOLUTION,
                self.tr("Temporal resolution (for station network)"),
                options=self.RES_OPTIONS,
                defaultValue=1,  # hourly
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                self.P_WIND_MODE,
                self.tr("Wind mode"),
                options=self.WIND_MODE_OPTIONS,
                defaultValue=0,
            )
        )

        self.addParameter(
            QgsProcessingParameterCrs(
                self.P_CRS,
                self.tr("Target CRS"),
                defaultValue="EPSG:4326",
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.P_SINK,
                self.tr("DWD stations"),
                QgsProcessing.TypeVectorPoint,
            )
        )

    # ------------------------------------------------------------------
    # kleine Helper
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_name_state(name: str, state: str):
        """
        Fix for cases where state is empty/'Frei' and the federal state
        is appended to the station name (e.g. 'Artern Thüringen').
        Returns (name, state).
        """
        name = (name or "").strip()
        state = (state or "").strip()

        # treat 'Frei' as missing (as observed in your data)
        if state.lower() in {"frei", ""} and name:
            # German federal states (Bundesländer)
            states = [
                "Baden-Württemberg",
                "Bayern",
                "Berlin",
                "Brandenburg",
                "Bremen",
                "Hamburg",
                "Hessen",
                "Mecklenburg-Vorpommern",
                "Niedersachsen",
                "Nordrhein-Westfalen",
                "Rheinland-Pfalz",
                "Saarland",
                "Sachsen",
                "Sachsen-Anhalt",
                "Schleswig-Holstein",
                "Thüringen",
            ]

            # longest first (important for hyphenated names like Mecklenburg-Vorpommern)
            for st in sorted(states, key=len, reverse=True):
                suffix = " " + st
                if name.endswith(suffix):
                    return name[: -len(suffix)].strip(), st

        return name, state

    @staticmethod
    def _dt_to_str(value):
        if value is None:
            return ""
        try:
            return value.strftime("%Y-%m-%d")
        except Exception:
            return str(value)

    # ------------------------------------------------------------------
    # Hauptlogik
    # ------------------------------------------------------------------
    def processAlgorithm(self, parameters, context, feedback):
        # Name-Filter
        search_text = (self.parameterAsString(parameters, self.P_SEARCH, context) or "").strip()
        name_filter = search_text if search_text else None

        # Extent (Projekt-CRS)
        extent = self.parameterAsExtent(parameters, self.P_EXTENT, context)
        has_extent = bool(extent) and (not extent.isEmpty())

        # Zeitfilter
        start_obj = self.parameterAsDateTime(parameters, self.P_START, context)
        end_obj = self.parameterAsDateTime(parameters, self.P_END, context)
        start_dt = start_obj.toPyDateTime() if start_obj else None
        end_dt = end_obj.toPyDateTime() if end_obj else None

        if start_dt and end_dt and end_dt <= start_dt:
            raise QgsProcessingException("End date must be after start date.")

        # Auflösung
        res_idx = self.parameterAsEnum(parameters, self.P_RESOLUTION, context)
        if res_idx not in self.RES_MAP:
            raise QgsProcessingException("Invalid resolution selection.")
        res_key = self.RES_MAP[res_idx]

        if res_key in {"daily", "monthly"}:
            raise QgsProcessingException(
                "Daily/monthly station metadata is not yet implemented.\n"
                "Please use 10-minute or hourly for station selection."
            )

        # Windmodus
        wind_idx = self.parameterAsEnum(parameters, self.P_WIND_MODE, context)
        if wind_idx not in self.WIND_MODE_MAP:
            raise QgsProcessingException("Invalid wind mode selection.")
        wind_mode = self.WIND_MODE_MAP[wind_idx]

        # Gusts -> 10-Minuten
        effective_res_key = res_key
        if wind_mode == "wind_gust_max":
            if res_key != "minute_10":
                feedback.pushInfo("Maximum wind selected → forcing 10-minute resolution.")
            effective_res_key = "minute_10"

        # Ziel-CRS
        target_crs = self.parameterAsCrs(parameters, self.P_CRS, context)
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")

        # Felder
        fields = QgsFields()
        fields.append(QgsField("station_id", QVariant.String))
        fields.append(QgsField("name", QVariant.String))
        fields.append(QgsField("state", QVariant.String))
        fields.append(QgsField("height_m", QVariant.Double))
        fields.append(QgsField("from_date", QVariant.String))
        fields.append(QgsField("to_date", QVariant.String))
        fields.append(QgsField("latitude", QVariant.Double))
        fields.append(QgsField("longitude", QVariant.Double))

        (sink, dest) = self.parameterAsSink(
            parameters,
            self.P_SINK,
            context,
            fields,
            QgsWkbTypes.Point,
            target_crs,
        )
        if sink is None:
            raise QgsProcessingException("Could not create output sink.")

        feedback.pushInfo("Querying DWD CDC station metadata …")

        # Extent -> WGS84 (für Filter)
        bbox_ll = None
        if has_extent:
            project_crs = context.project().crs() if context.project() else target_crs
            tr_to_wgs = QgsCoordinateTransform(
                project_crs, wgs84, context.transformContext()
            )
            rect_ll = tr_to_wgs.transformBoundingBox(extent)
            bbox_ll = (
                rect_ll.xMinimum(),
                rect_ll.yMinimum(),
                rect_ll.xMaximum(),
                rect_ll.yMaximum(),
            )
            feedback.pushInfo(
                f"Using extent filter in WGS84: "
                f"{bbox_ll[0]:.4f}, {bbox_ll[1]:.4f}, {bbox_ll[2]:.4f}, {bbox_ll[3]:.4f}"
            )
        else:
            feedback.pushInfo("No extent filter set → using full station network.")

        # --- 1. Stationen vom DWD holen ------------------------------------
        try:
            all_records = dwd_cdc.get_wind_station_metadata(
                resolution=effective_res_key,
                wind_mode=wind_mode,
                feedback=feedback,
            )
        except Exception as e:
            raise QgsProcessingException(
                f"Could not query DWD CDC station metadata: {e}"
            )

        feedback.pushInfo(f"Fetched {len(all_records)} stations from DWD CDC (raw).")

        # --- 2. Filtern (Name/BBOX/Zeit) -----------------------------------
        records = dwd_cdc.filter_stations(
            records=all_records,
            name_search=name_filter,
            bbox=bbox_ll,
            start_date=start_dt,
            end_date=end_dt,
        )

        feedback.pushInfo(f"{len(records)} stations remain after filtering.")

        if not records:
            raise QgsProcessingException(
                "No DWD stations found matching the given criteria.\n"
                "Try relaxing name, extent or date filters."
            )

        # Debug: Beispiel
        sample = records[0]
        feedback.pushInfo(
            f"Sample station: ID={sample.get('station_id')} "
            f"Name={sample.get('name')} "
            f"lat={sample.get('latitude')} lon={sample.get('longitude')}"
        )

        # --- 3. Features bauen (WGS84 -> Ziel-CRS) -------------------------
        tr_to_target = QgsCoordinateTransform(
            wgs84, target_crs, context.transformContext()
        )

        total = len(records)
        added = 0
        skipped_no_coord = 0
        skipped_invalid = 0
        add_errors = 0

        for i, rec in enumerate(records):
            if feedback.isCanceled():
                break
            if total:
                feedback.setProgress(int(100.0 * i / total))

            stid = str(rec.get("station_id", "")).strip()
            name_raw = str(rec.get("name", "")).strip()
            state_raw = str(rec.get("state", "")).strip()
            name, state = self._normalize_name_state(name_raw, state_raw)


            h = rec.get("height", None)
            try:
                h = float(h) if h is not None else None
            except Exception:
                h = None

            la = rec.get("latitude", None)
            lo = rec.get("longitude", None)

            if la is None or lo is None:
                skipped_no_coord += 1
                continue

            # Koordinaten defensiv in float konvertieren
            try:
                la = float(str(la).replace(",", "."))
                lo = float(str(lo).replace(",", "."))
            except Exception as e:
                skipped_invalid += 1
                QgsMessageLog.logMessage(
                    f"Skipping station {stid} due to invalid coordinates: {e}",
                    "DWD Station Finder",
                )
                continue

            frm = rec.get("start_date", None)
            to = rec.get("end_date", None)

            # WGS84 -> Ziel-CRS
            try:
                pt_wgs = QgsPointXY(lo, la)
                pt_tgt = tr_to_target.transform(pt_wgs)
                geom = QgsGeometry.fromPointXY(pt_tgt)
            except Exception as e:
                skipped_invalid += 1
                QgsMessageLog.logMessage(
                    f"Skipping station {stid} due to transform error: {e}",
                    "DWD Station Finder",
                )
                continue

            f = QgsFeature(fields)
            f.setGeometry(geom)
            f["station_id"] = stid.zfill(5) if stid.isdigit() else stid
            f["name"] = name
            f["state"] = state
            f["height_m"] = h
            f["from_date"] = self._dt_to_str(frm)
            f["to_date"] = self._dt_to_str(to)
            f["latitude"] = la
            f["longitude"] = lo

            try:
                ok = sink.addFeature(f)
                if ok:
                    added += 1
                else:
                    add_errors += 1
            except Exception as e:
                add_errors += 1
                QgsMessageLog.logMessage(
                    f"Error adding feature for station {stid}: {e}",
                    "DWD Station Finder",
                )

        feedback.pushInfo(
            f"Added {added} features. "
            f"Skipped (no coords): {skipped_no_coord}, "
            f"Skipped (invalid/transform): {skipped_invalid}, "
            f"Add errors: {add_errors}."
        )

        if added == 0:
            raise QgsProcessingException(
                "No features were added to the output layer. "
                "Check the log panel for details."
            )

        return {self.P_SINK: dest}
