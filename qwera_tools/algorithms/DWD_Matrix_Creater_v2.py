# -*- coding: utf-8 -*-
try:
    from . import dwd_cdc
except Exception:
    import dwd_cdc

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtGui import QImage
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterString,
    QgsProcessingParameterDateTime,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterField,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterEnum,
    QgsProcessingException,
    QgsVectorLayer,
    QgsFeatureRequest,
    QgsApplication,
)
import os, tempfile, csv
import math
from datetime import datetime


class DwdWindFrequency(QgsProcessingAlgorithm):
    # Parameter keys
    P_STATIONS = "stations"
    P_STATION_LAYER = "station_layer"
    P_STATION_ID_FIELD = "station_id_field"
    P_USE_SELECTION = "use_selection"
    P_START = "start"
    P_END = "end"
    P_RESOLUTION = "resolution"
    # NEW: wind statistic selector
    P_WIND_MODE = "wind_mode"
    P_SECTORS = "sectors"
    P_SPEED_BINS = "speed_bins"
    P_AUTOBIN_WIDTH = "autobin_width"
    # Raw data-Flags
    P_EXPORT_RAW = "export_raw"
    P_EXPORT_RAW_SPLIT = "export_raw_split"
    P_OUT_DIR = "out_dir"
    P_PLOTS = "make_plots"
    P_PREFIX = "file_prefix"
    # Custom-Filter
    P_FILTER_MONTHS = "filter_months"
    P_GROUP_STATIONS_ONE = "group_stations_one"
    # additional Output
    P_OUT_ALL_LONG = "out_all_long"
    P_OUT_ALL_MATRIX = "out_all_matrix"
    P_OUT_MONTH_LONG = "out_month_long"
    P_OUT_MONTH_MATRIX = "out_month_matrix"
    P_OUT_SEASON_LONG = "out_season_long"
    P_OUT_SEASON_MATRIX = "out_season_matrix"
    P_OUT_CUSTOM_LONG = "out_custom_long"
    P_OUT_CUSTOM_MATRIX = "out_custom_matrix"

    # global delimiter for all csv exports
    CSV_DELIM = ";"

    # Selection for resolution (Display → wetterdienst key)
    RES_LABELS = ["10-minute", "hourly", "daily", "monthly"]
    RES_MAP    = {0: "minute_10", 1: "hourly", 2: "daily", 3: "monthly"}

    # NEW: selection for type of wind statistic
    WIND_MODE_LABELS = [
        "Mean wind speed (FF = wind_speed)",
        "Maximum wind gust (FX = wind_gust_max)",
    ]

    def icon(self):
        icon_path = os.path.join(os.path.dirname(__file__), "..", "icons", "qwera_tool_0.svg")
        return QIcon(icon_path)

    def tr(self, text):
        return QCoreApplication.translate("DwdWindFrequency", text)

    def createInstance(self):
        return DwdWindFrequency()

    def name(self):
        return "dwd_wind_frequency"

    def displayName(self):
        return self.tr("DWD – Downloader and Wind Frequency Matrices Creater")

    def group(self):
        return ("Additional Tools")

    def groupId(self):
        return "additional_tools"

    # --- keep original help text exactly as provided ---
    def shortHelpString(self):
        return """
            <h2>Description</h2>
            <p>
            This tool downloads <b>wind data (FF = wind_speed, DD = wind_direction)</b> from the <b>Deutscher Wetterdienst (DWD)</b>, calculates <b>wind-frequency matrices</b> (by direction sector and speed class), and exports results in multiple CSV formats. 
            It supports per-station, monthly, seasonal, and user-defined “custom” aggregations — optionally visualized as wind-rose plots. Station-Id's can be derived from a layer or manually entered. A specified time range of interest can be defined. 
            </p>

            <h2>Standards & References</h2>
            <dt><ul>
            <li><b><a href="https://www.dwd.de/EN/Home/home_node.html">Deutscher Wetterdienst (DWD) Open Data</a></b> — official meteorological observation source.</li>
            <li><b><a href="https://pypi.org/project/wetterdienst/">Wetterdienst Python package</a></b> — used for automated DWD data requests.</li>
            <li><b><a href="https://www.sciencedirect.com/science/article/pii/S2215016124004576">Funk &amp; V&ouml;lker (2024)</a></b>, “A GIS-toolbox for a landscape structure based Wind Erosion Risk Assessment (WERA)” — describes the methodological context of using DWD wind statistics for erosion risk modeling.</li>
            </ul></dt>

        
            <h2>Inputs</h2>
            <dt><ul>
            <li><b>Station layer (optional)</b> — vector layer with station IDs.</li>
            <li><b>ID field</b> — attribute containing the DWD station ID.</li>
            <li><b>Manual station IDs</b> — comma-separated list (e.g. 04036, 05084).</li>
            <li><b>Start / End date</b> — UTC time period for data retrieval.</li>
            <li><b>Temporal resolution</b> — 10-minute, hourly, daily, or monthly.</li>
            <li><b>Wind mode</b> — Either “mean wind speed” or “maximum wind gust” can be selected. If “maximum wind gust” has been selected it overwrites the Temporal resolution since wind gust data is only available for the 10-minute resolution.</li>
            <li><b>Number of sectors</b> — Descriptes the number of equal sectores the direction rose will be devided in. e.g. 36 for 10° resolution. Must be between 4 and 72. Recommented is 36. </li>
            <li><b>Speed class limits</b> — optional manual bin limits (m/s), otherwise auto-binned. (e.g. 2,6,8,10,15,...)</li>
            <li><b>Auto-binning step size</b> — step size (m/s) if classes are not defined.</li>
            <li><b>Month filter</b> — comma-separated months (1–12) for custom aggregation. (e.g. 3,4,5, aggregats only March, April, and May throughout the years)</li>
            <li><b>Group stations</b> — treat all selected stations as one (for regional averages).</li>
            <li><b>Output folder</b> — directory for all CSV and PNG results.</li>
            <li><b>Windrose plots</b> — optional visual output (one PNG per station).</li>
            <li><b>Filename prefix</b> — custom name prefix for exported files.</li>
            </ul></dt>

            <h2>Outputs</h2>
            <dt><ul>
            <li><b>Speed-info CSV</b> — summary with n, ff_min, ff_mean, ff_max, ff_p90, ff_p95 per station and overall.</li>
            <li><b>Frequency CSVs</b> — optional exports in both long (tidy) and matrix forms:
                <dd><ul style="list-style-type:square;">
                <li>Overall (per station)</li>
                <li>Monthly (per station × month)</li>
                <li>Seasonal (per station × season)</li>
                <li>Custom (filtered months, optionally grouped stations)</li>
                <li> INFO: ALL Matrix-Output can be used as input for the Wind statistics & shadow parameters Tool.</li>
                </ul></dd>
            <dt><ul>
            <li><b>Raw data CSV</b> — combined file of all wind observations (optional).</li>
            <li><b>Per-station raw CSVs</b> — one file per station (optional).</li>
            <li><b>Windrose PNGs</b> — one per station if plotting is enabled.</li>
            </ul></dt>

            <h2>Notes</h2>
            <dt><ul>
            <li>Only stations with available wind data within the selected options are processed.</li>
            <li>Requires internet access.</li>
            <li>All CSVs use numeric upper bin edges for sectors and speed classes.</li>
            <li>ChatGPT was used to create this plugin.</li>
            <li>Tested with QGIS 3.44.x (Python 3.12, Windows).</li>
            </ul></dt>
        """

    # ---------- Parameter UI ----------
    def initAlgorithm(self, config=None):
        p_layer = QgsProcessingParameterVectorLayer(
            self.P_STATION_LAYER, self.tr("Stations-Layer"), types=[QgsProcessing.TypeVectorPoint]
        )
        p_layer.setFlags(p_layer.flags() | QgsProcessingParameterDefinition.FlagOptional)
        self.addParameter(p_layer)

        p_field = QgsProcessingParameterField(
            self.P_STATION_ID_FIELD, self.tr("ID field in station-layer"),
            parentLayerParameterName=self.P_STATION_LAYER, optional=True
        )
        self.addParameter(p_field)

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.P_USE_SELECTION, self.tr("Use only selection from station layer"), defaultValue=False
            )
        )

        p_ids = QgsProcessingParameterString(
            self.P_STATIONS, self.tr("Additional DWD station IDs (comma-separated)"),
            defaultValue=None
        )
        p_ids.setFlags(p_ids.flags() | QgsProcessingParameterDefinition.FlagOptional)
        self.addParameter(p_ids)

        self.addParameter(
            QgsProcessingParameterDateTime(self.P_START, self.tr("Start date (UTC)"),
                                           type=QgsProcessingParameterDateTime.DateTime)
        )
        self.addParameter(
            QgsProcessingParameterDateTime(self.P_END, self.tr("End date (UTC)"),
                                           type=QgsProcessingParameterDateTime.DateTime)
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                self.P_RESOLUTION, self.tr("Temporal resolution"),
                options=self.RES_LABELS, allowMultiple=False, defaultValue=1
            )
        )

        # NEW: choose between mean wind and maximum wind
        self.addParameter(
            QgsProcessingParameterEnum(
                self.P_WIND_MODE,
                self.tr("Wind mode"),
                options=self.WIND_MODE_LABELS,
                allowMultiple=False,
                defaultValue=0,  # 0 = mean wind, 1 = maximum wind
            )
        )

        self.addParameter(
            QgsProcessingParameterNumber(
                self.P_SECTORS, self.tr("Number of Sectors (e.g.: 16 → 22.5°; min: 4; max: 72)"),
                type=QgsProcessingParameterNumber.Integer, minValue=4, maxValue=72, defaultValue=16
            )
        )

        p_bins = QgsProcessingParameterString(
            self.P_SPEED_BINS,
            self.tr("Speed class limits (m/s, decimal point; blank = auto binning)"),
            defaultValue=None,
        )
        p_bins.setFlags(p_bins.flags() | QgsProcessingParameterDefinition.FlagOptional)
        self.addParameter(p_bins)

        self.addParameter(
            QgsProcessingParameterNumber(
                self.P_AUTOBIN_WIDTH, self.tr("Auto-binning step size (m/s; used when classes are empty)"),
                type=QgsProcessingParameterNumber.Double, defaultValue=1.0, minValue=0.1
            )
        )

        p_months = QgsProcessingParameterString(
            self.P_FILTER_MONTHS,
            self.tr("Custom Aggregation: Filter months (comma -delimited, 1..12; empty = all)"),
            defaultValue="3,4,5",
        )
        p_months.setFlags(p_months.flags() | QgsProcessingParameterDefinition.FlagOptional)
        self.addParameter(p_months)

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.P_GROUP_STATIONS_ONE,
                self.tr("Group stations: Combine selected stations into one station (ignore ID)"),
                defaultValue=True,
            )
        )

        self.addParameter(
            QgsProcessingParameterFolderDestination(self.P_OUT_DIR, self.tr("Output folder (not TEMPORARY_OUTPUT)"))
        )
        self.addParameter(
            QgsProcessingParameterBoolean(self.P_PLOTS, self.tr("Create wind rose PNGs"), defaultValue=False)
        )
        self.addParameter(
            QgsProcessingParameterString(self.P_PREFIX, self.tr("File prefix"), optional=True)
        )

        # --- Extended output flags (advanced) ---
        for key, label, default in [
            (self.P_OUT_ALL_LONG,   self.tr("CSV: Total frequencies (Long)"), False),
            (self.P_OUT_ALL_MATRIX, self.tr("CSV: Total frequencies (matrix)"), False),
            (self.P_OUT_MONTH_LONG,   self.tr("CSV: Frequencies monthly (Long)"), False),
            (self.P_OUT_MONTH_MATRIX, self.tr("CSV: Frequencies per month (matrix)"), False),
            (self.P_OUT_SEASON_LONG,   self.tr("CSV: Frequencies seasonal (Long)"), False),
            (self.P_OUT_SEASON_MATRIX, self.tr("CSV: Frequencies seasonal (matrix)"), False),
            (self.P_OUT_CUSTOM_LONG,   self.tr("CSV: Custom frequencies (Long)"), False),
            (self.P_OUT_CUSTOM_MATRIX, self.tr("CSV: Custom frequencies (matrix) INPUT FOR WIND STATISTIC TOOL"), True),
            (self.P_EXPORT_RAW,        self.tr("CSV: Total raw data (one file)"), True),
            (self.P_EXPORT_RAW_SPLIT,  self.tr("CSV: Raw data per station (multiple files)"), True),
        ]:
            p = QgsProcessingParameterBoolean(key, label, defaultValue=default)
            p.setFlags(p.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
            self.addParameter(p)

    # ---------- Light deps ----------
 
    @staticmethod
    def _normalize_station_id(v, width=5):
        """
        Normalize DWD station id to a zero-padded string (default width=5).
        Handles int/float/string and strips whitespace. Keeps non-digit IDs as-is.
        """
        if v is None:
            return ""
        s = str(v).strip()

        # Handle common "numeric" representations (e.g. 4036.0)
        # Only convert if it is clearly numeric.
        try:
            f = float(s.replace(",", "."))  # tolerate decimal comma
            if f.is_integer():
                s = str(int(f))
        except Exception:
            pass

        s = s.strip()
        if s.isdigit():
            return s.zfill(width)
        return s


    @staticmethod
    def _parse_speed_bins(s: str):
        vals = []
        if s:
            for t in (s or "").split(","):
                t = t.strip()
                if t:
                    vals.append(float(t))
        return vals

    @staticmethod
    def _parse_month_list(month_str: str):
        months = []
        if month_str:
            for t in month_str.split(','):
                t = t.strip()
                if t:
                    m = int(t)
                    if 1 <= m <= 12:
                        months.append(m)
        return sorted(set(months))

    # ----- Binning / frequency helpers (pure Python) -----
    @staticmethod
    def _sector_upper(dd, n_sect):
        """Return sector upper edge in degrees for a given direction dd in [0,360)."""
        if dd < 0 or dd >= 360:
            dd = dd % 360.0
        width = 360.0 / n_sect
        # include_lowest=True, right=False behaviour: 0° belongs to first bin [0,width)
        k = int(dd // width)
        upper = (k + 1) * width
        # cap numerical noise
        if upper > 360.0 and upper - 360.0 < 1e-9:
            upper = 360.0
        return round(upper, 6)

    @staticmethod
    def _vclass_upper(ff, edges):
        """Return the upper edge for speed ff using half-open bins [edge[i], edge[i+1]). edges must end with inf."""
        if ff is None:
            return None
        for i in range(len(edges) - 1):
            lo, hi = edges[i], edges[i + 1]
            if ff >= lo and ff < hi:
                return hi
        # if ff >= last but last is inf, return inf
        return edges[-1]

    @staticmethod
    def _group_key(row, extra=None):
        k = [row["station_id"]]
        if extra:
            for c in extra:
                k.append(row[c])
        return tuple(k)

    @staticmethod
    def _freq_long_plain(rows, n_sect, edges, extra_dims=None):
        """
        rows: list of dicts with keys: station_id, date, ff, dd (+ optional extra fields)
        Returns list of dicts: {station_id, [extra...], sector, vclass, n, pct}
        sector/vclass are numeric upper edges.
        """
        counts = {}
        totals = {}
        extra_dims = extra_dims or []

        for r in rows:
            ff = r["ff"]; dd = r["dd"]
            if ff is None or dd is None:
                continue
            if ff < 0:
                continue
            dd = dd % 360.0
            sec_up = DwdWindFrequency._sector_upper(dd, n_sect)
            v_up = DwdWindFrequency._vclass_upper(ff, edges)
            gk = DwdWindFrequency._group_key(r, extra_dims)

            totals[gk] = totals.get(gk, 0) + 1
            key = (gk, sec_up, v_up)
            counts[key] = counts.get(key, 0) + 1

        out = []
        for (gk, sec_up, v_up), n in counts.items():
            total = totals.get(gk, 0) or 1
            pct = round(100.0 * n / total, 6)
            rec = {"station_id": gk[0]}
            # add extra dim labels back
            for i, dim in enumerate(extra_dims, start=1):
                rec[dim] = gk[i]
            rec.update({"sector": sec_up, "vclass": v_up, "n": n, "pct": pct})
            out.append(rec)
        return out

    @staticmethod
    def _freq_matrix_from_long_plain(long_rows, extra_dims=None, value_col="n"):
        """
        Convert long rows to a matrix-like flat table.
        Rows grouped by extra_dims + vclass; columns are sector upper edges.
        Returns (header, rows) ready for CSV.
        """
        extra_dims = extra_dims or []
        # collect unique sorted sets
        sectors = sorted({r["sector"] for r in long_rows if r.get("sector") is not None})
        vclasses = sorted({r["vclass"] for r in long_rows if r.get("vclass") is not None})

        # group rows by (extra_dims..., vclass)
        groups = {}
        for r in long_rows:
            key = tuple(r.get(dim) for dim in extra_dims) + (r["vclass"],)
            groups.setdefault(key, {})[r["sector"]] = r.get(value_col, 0)

        header = [*extra_dims, "vclass"] + [str(s) for s in sectors]
        out_rows = []
        for key in sorted(groups.keys()):
            row = list(key)
            cells_map = groups[key]
            for s in sectors:
                row.append(cells_map.get(s, 0))
            out_rows.append(row)
        return header, out_rows

    # ---------- Main ----------
    def processAlgorithm(self, parameters, context, feedback):

        # inputs
        vl = self.parameterAsVectorLayer(parameters, self.P_STATION_LAYER, context)
        id_field = self.parameterAsString(parameters, self.P_STATION_ID_FIELD, context)
        use_sel = self.parameterAsBool(parameters, self.P_USE_SELECTION, context)

        manual_raw = self.parameterAsString(parameters, self.P_STATIONS, context)
        manual_ids_raw = [x.strip() for x in (manual_raw or "").split(",") if x and x.strip()]
        manual_ids = [self._normalize_station_id(x) for x in manual_ids_raw if self._normalize_station_id(x)]

        layer_ids_raw = dwd_cdc.station_ids_from_layer(vl, id_field, use_sel, feedback) if vl else []
        layer_ids = [self._normalize_station_id(x) for x in layer_ids_raw if self._normalize_station_id(x)]

        stations = sorted(set(layer_ids) | set(manual_ids))
        if not stations:
            raise QgsProcessingException(
                "No station IDs found.\n"
                "- Select a station layer + ID field (optional: selection only), and/or\n"
                "- enter IDs manually (comma-separated)."
            )

        start_dt = self.parameterAsDateTime(parameters, self.P_START, context).toPyDateTime()
        end_dt   = self.parameterAsDateTime(parameters, self.P_END, context).toPyDateTime()
        if end_dt <= start_dt:
            raise QgsProcessingException("The end date must be after the start date (select a valid time window).")

        n_sect = int(self.parameterAsInt(parameters, self.P_SECTORS, context))
        res_idx = self.parameterAsEnum(parameters, self.P_RESOLUTION, context)
        if res_idx not in self.RES_MAP:
            raise QgsProcessingException("Invalid resolution selection.")
        res_key = self.RES_MAP[res_idx]

        # NEW: wind statistic mode → which DWD parameter is used as "ff"
        wind_mode = self.parameterAsEnum(parameters, self.P_WIND_MODE, context)
        if wind_mode == 0:
            ff_param_name = "wind_speed"      # mean wind (FF)
        else:
            ff_param_name = "wind_gust_max"   # maximum wind (FX)

        use_max_wind = (wind_mode == 1)
        if use_max_wind:
            # NOTE: resolution key for 10-minute data in wetterdienst is "minute_10"
            if res_key != "minute_10":
                feedback.pushInfo(
                    "Maximum wind selected → forcing resolution to 'minute_10' "
                    "(wind_extreme is only available at 10-minute resolution)."
                )
            res_key = "minute_10"

        speed_bins_raw = self.parameterAsString(parameters, self.P_SPEED_BINS, context)
        speed_bins_str = (speed_bins_raw or "").strip()
        autobin_width = float(self.parameterAsDouble(parameters, self.P_AUTOBIN_WIDTH, context))

        export_raw_combined = self.parameterAsBool(parameters, self.P_EXPORT_RAW, context)
        export_raw_split    = self.parameterAsBool(parameters, self.P_EXPORT_RAW_SPLIT, context)

        filter_months_raw = self.parameterAsString(parameters, self.P_FILTER_MONTHS, context)
        filter_months = self._parse_month_list(filter_months_raw)
        group_stations_one = self.parameterAsBool(parameters, self.P_GROUP_STATIONS_ONE, context)

        make_plots = self.parameterAsBool(parameters, self.P_PLOTS, context)
        prefix_in = (self.parameterAsString(parameters, self.P_PREFIX, context) or "").strip()

        # default prefix depends on wind mode
        if prefix_in:
            prefix = prefix_in
        else:
            prefix = "dwd_wind" if wind_mode == 0 else "dwd_wind_max"

        out_dir_in = self.parameterAsString(parameters, self.P_OUT_DIR, context)
        if not out_dir_in or out_dir_in.upper() == "TEMPORARY_OUTPUT":
            out_dir = tempfile.mkdtemp(prefix=prefix)
            feedback.pushInfo(f"Attention: TEMPORARY_OUTPUT detected — use temp folder: {out_dir}")
        else:
            out_dir = out_dir_in
            if not os.path.isdir(out_dir):
                os.makedirs(out_dir, exist_ok=True)

        # ---- DWD aus CDC laden ----
        feedback.pushInfo(
            f"CDC: Loading {self.RES_LABELS[res_idx]} data for "
            f"{len(stations)} station(s): {', '.join(stations[:10])}…"
        )

        try:
            ts = dwd_cdc.get_wind_timeseries_from_cdc(
                station_ids=stations,
                start=start_dt,
                end=end_dt,
                resolution=res_key,
                wind_mode=ff_param_name,  # 'wind_speed' oder 'wind_gust_max'
                feedback=feedback,
            )
        except Exception as e:
            feedback.reportError(f"CDC: Error while fetching data: {e}")
            raise QgsProcessingException(
                "Error while loading data from DWD CDC.\n"
                "Check station IDs, time window and internet connection."
            )

        if not ts:
            raise QgsProcessingException("No valid (speed+direction) pairs after CDC download.")
        
        for r in ts:
            r["station_id"] = self._normalize_station_id(r.get("station_id"))

        ts.sort(key=lambda x: (x["station_id"], x["date"]))

        # ---- speed-info ----
        from statistics import mean
        speeds_by_sid = {}
        for r in ts:
            speeds_by_sid.setdefault(r["station_id"], []).append(r["ff"])

        speed_rows = []
        all_vals = []
        for sid, vals in speeds_by_sid.items():
            if not vals:
                continue
            all_vals.extend(vals)
            speed_rows.append([
                sid, len(vals), float(min(vals)), float(mean(vals)), float(max(vals)),
                dwd_cdc.percentile_inc(vals, 0.90),
                dwd_cdc.percentile_inc(vals, 0.95),
            ])

        overall_row = [
            "__ALL__", len(all_vals),
            float(min(all_vals)) if all_vals else "",
            float(mean(all_vals)) if all_vals else "",
            float(max(all_vals)) if all_vals else "",
            dwd_cdc.percentile_inc(all_vals, 0.90),
            dwd_cdc.percentile_inc(all_vals, 0.95),
        ]
        speed_rows.append(overall_row)

        out_speed_info = os.path.join(out_dir, f"{prefix}_speed_info.csv")
        dwd_cdc.write_csv(out_speed_info,
                        ["station_id", "n", "ff_min", "ff_mean", "ff_max", "ff_p90", "ff_p95"],
                        speed_rows, self.CSV_DELIM)
        feedback.pushInfo(f"Speed-Info written: {out_speed_info}")

        # ---- determine speed classes (edges) ----
        edges = self._parse_speed_bins(speed_bins_str)
        if edges:
            feedback.pushInfo(f"Use manual classes: {edges} (+∞)")
        else:
            if autobin_width <= 0:
                raise QgsProcessingException("Auto-Binning: Step size must be > 0 or specify classes manually.")
            gmax = max((r["ff"] for r in ts), default=0.0)
            import math as _m
            top = _m.ceil(gmax / autobin_width) * autobin_width
            edges = [0.0]
            x = 0.0
            while x < top - 1e-12:
                x = round(x + autobin_width, 6)
                edges.append(x)
            feedback.pushInfo(f"Auto-Binning: Step={autobin_width} m/s, edges 0..{top} → {edges} (+∞)")
        if not math.isinf(edges[-1]):
            edges = edges + [float("inf")]

        # annotate month/season
        for r in ts:
            m = r["date"].month
            r["month"] = m
            r["season"] = "DJF" if m in (12, 1, 2) else ("MAM" if m in (3, 4, 5)
                             else ("JJA" if m in (6, 7, 8) else "SON"))

        # output flags
        want_all_long   = self.parameterAsBool(parameters, self.P_OUT_ALL_LONG, context)
        want_all_matrix = self.parameterAsBool(parameters, self.P_OUT_ALL_MATRIX, context)
        want_mon_long   = self.parameterAsBool(parameters, self.P_OUT_MONTH_LONG, context)
        want_mon_matrix = self.parameterAsBool(parameters, self.P_OUT_MONTH_MATRIX, context)
        want_sea_long   = self.parameterAsBool(parameters, self.P_OUT_SEASON_LONG, context)
        want_sea_matrix = self.parameterAsBool(parameters, self.P_OUT_SEASON_MATRIX, context)
        want_cus_long   = self.parameterAsBool(parameters, self.P_OUT_CUSTOM_LONG, context)
        want_cus_matrix = self.parameterAsBool(parameters, self.P_OUT_CUSTOM_MATRIX, context)

        results = {"OUT_DIR": out_dir, "SPEED_INFO_CSV": out_speed_info}

        # ---- 1) Total by station ----
        if want_all_long or want_all_matrix:
            feedback.pushInfo("Aggregate frequencies (total, per station) …")
            long_all = self._freq_long_plain(ts, n_sect, edges, extra_dims=None)  # extra None → just station_id
            if want_all_long:
                # out_all_long = os.path.join(out_dir, f"{prefix}_frequency_by_station.csv")
                # header = ["station_id", "sector", "vclass", "n", "pct"]
                # rows = [{
                #     "station_id": r["station_id"],
                #     "date": r["date"].isoformat(),
                #     "w_speed": r["ff"],
                #     "w_dir": r["dd"],
                #     "qn_speed": r.get("qn_ff", ""),
                #     "qn_dir": r.get("qn_dd", ""),
                # } for r in ts]

                # dwd_cdc.write_csv(
                #     raw_path,
                #     ["station_id", "date", "w_speed", "w_dir", "qn_speed", "qn_dir"],
                #     rows,
                #     self.CSV_DELIM,
                # )
                # results["CSV_ALL"] = out_all_long
                out_all_long = os.path.join(out_dir, f"{prefix}_frequency_by_station.csv")
                header = ["station_id", "sector", "vclass", "n", "pct"]
                dwd_cdc.write_csv(out_all_long, header, long_all, self.CSV_DELIM)
                results["CSV_ALL"] = out_all_long
            if want_all_matrix:
                header, rows = self._freq_matrix_from_long_plain(long_all, extra_dims=["station_id"], value_col="n")
                out_all_mat = os.path.join(out_dir, f"{prefix}_matrix_by_station.csv")
                dwd_cdc.write_csv(out_all_mat, header, rows, self.CSV_DELIM)
                results["CSV_ALL_MATRIX"] = out_all_mat

        # ---- 2) Monthly per station ----
        if want_mon_long or want_mon_matrix:
            feedback.pushInfo("Aggregate frequencies (monthly, per station) …")
            # split by (station_id, month)
            long_mon = self._freq_long_plain(ts, n_sect, edges, extra_dims=["month"])
            if want_mon_long:
                out_mon_long = os.path.join(out_dir, f"{prefix}_frequency_by_month.csv")
                header = ["station_id", "month", "sector", "vclass", "n", "pct"]
                rows = [[r["station_id"], r["month"], r["sector"], r["vclass"], r["n"], r["pct"]] for r in long_mon]
                dwd_cdc.write_csv(out_mon_long, header, rows, self.CSV_DELIM)
                results["CSV_MONTH"] = out_mon_long
            if want_mon_matrix:
                header, rows = self._freq_matrix_from_long_plain(long_mon, extra_dims=["station_id", "month"], value_col="n")
                out_mon_mat = os.path.join(out_dir, f"{prefix}_matrix_by_month.csv")
                dwd_cdc.write_csv(out_mon_mat, header, rows, self.CSV_DELIM)
                results["CSV_MONTH_MATRIX"] = out_mon_mat

        # ---- 3) Seasonal per station ----
        if want_sea_long or want_sea_matrix:
            feedback.pushInfo("Aggregate frequencies (seasonal, per station) …")
            long_sea = self._freq_long_plain(ts, n_sect, edges, extra_dims=["season"])
            if want_sea_long:
                out_sea_long = os.path.join(out_dir, f"{prefix}_frequency_by_season.csv")
                header = ["station_id", "season", "sector", "vclass", "n", "pct"]
                rows = [[r["station_id"], r["season"], r["sector"], r["vclass"], r["n"], r["pct"]] for r in long_sea]
                dwd_cdc.write_csv(out_sea_long, header, rows, self.CSV_DELIM)
                results["CSV_SEASON"] = out_sea_long
            if want_sea_matrix:
                header, rows = self._freq_matrix_from_long_plain(long_sea, extra_dims=["station_id", "season"], value_col="n")
                out_sea_mat = os.path.join(out_dir, f"{prefix}_matrix_by_season.csv")
                dwd_cdc.write_csv(out_sea_mat, header, rows, self.CSV_DELIM)
                results["CSV_SEASON_MATRIX"] = out_sea_mat

        # ---- 4) Custom: filter months & optionally group stations ----
        if want_cus_long or want_cus_matrix:
            if filter_months:
                feedback.pushInfo(f"Custom output: Filter months {filter_months} …")
                ts_custom = [r for r in ts if r["month"] in filter_months]
            else:
                ts_custom = list(ts)
            if not ts_custom:
                feedback.pushInfo("Custom output: no data in filter – skip.")
            else:
                if group_stations_one:
                    for r in ts_custom:
                        r = r  # just clarity
                        r["station_id"] = "__GROUP__"
                long_cus = self._freq_long_plain(ts_custom, n_sect, edges, extra_dims=None if group_stations_one else None)
                mon_label = "all" if not filter_months else "_".join([f"{m:02d}" for m in filter_months])
                grp_label = "grouped" if group_stations_one else "by_station"
                if want_cus_long:
                    out_cus_long = os.path.join(out_dir, f"{prefix}_frequency_custom_{grp_label}_m{mon_label}.csv")
                    header = ["station_id", "sector", "vclass", "n", "pct"]
                    rows = [[r["station_id"], r["sector"], r["vclass"], r["n"], r["pct"]] for r in long_cus]
                    dwd_cdc.write_csv(out_cus_long, header, rows, self.CSV_DELIM)
                    results["CSV_CUSTOM"] = out_cus_long
                if want_cus_matrix:
                    header, rows = self._freq_matrix_from_long_plain(long_cus, extra_dims=None if group_stations_one else ["station_id"], value_col="n")
                    out_cus_mat = os.path.join(out_dir, f"{prefix}_matrix_custom_{grp_label}_m{mon_label}_FOR_WIND_STAT_TOOL.csv")
                    dwd_cdc.write_csv(out_cus_mat, header, rows, self.CSV_DELIM)
                    results["CSV_CUSTOM_MATRIX"] = out_cus_mat

        # ---- Raw data exports ----
        # Now use FULL raw wetterdienst records (recs) with ALL columns (incl. quality etc.)
        if export_raw_combined:
            raw_path = os.path.join(out_dir, f"{prefix}_raw_timeseries.csv")
            header = ["station_id", "date", "w_speed", "w_dir", "qn_speed", "qn_dir"]
            rows = [
                [
                    r["station_id"],
                    r["date"].isoformat(),
                    r["ff"],
                    r["dd"],
                    r.get("qn_ff", ""),
                    r.get("qn_dd", ""),
                ]
                for r in ts
            ]
            dwd_cdc.write_csv(raw_path, header, rows, self.CSV_DELIM)
            feedback.pushInfo(f"Raw data (one file) written: {raw_path}")
            results["RAW_CSV"] = raw_path

        if export_raw_split:
            raw_dir = os.path.join(out_dir, f"{prefix}_raw_by_station")
            os.makedirs(raw_dir, exist_ok=True)
            by_sid = {}
            for r in ts:
                by_sid.setdefault(r["station_id"], []).append(r)
            files = []
            for sid, rows in by_sid.items():
                rows.sort(key=lambda x: x["date"])
                fpath = os.path.join(raw_dir, f"{prefix}_raw_{sid}.csv")
                dwd_cdc.write_csv(
                    fpath,
                    ["station_id", "date", "w_speed", "w_dir", "qn_speed", "qn_dir"],
                    [
                        [
                            sid,
                            r["date"].isoformat(),
                            r["ff"],
                            r["dd"],
                            r.get("qn_ff", ""),
                            r.get("qn_dd", ""),
                        ]
                        for r in rows
                    ],
                    self.CSV_DELIM
                )
                files.append(fpath)
            feedback.pushInfo(f"Raw data per station written in: {raw_dir} ({len(files)} files)")
            results["RAW_CSV_DIR"] = raw_dir
            results["RAW_CSV_LIST"] = ";".join(files)


        # ---- Optional wind-rose PNGs (no pandas) ----
        if make_plots:
            try:
                import math as _math
                import matplotlib.pyplot as plt
            except Exception as e:
                feedback.reportError(f"Matplotlib not available – skip wind-rose plots: {e}")
            else:
                feedback.pushInfo("Generate wind rose PNGs for each station …")
                # pre-aggregate percentage per station for stacked polar bar
                width = 2 * _math.pi / n_sect

                # --- PLOT classes (fixed) ---
                # 3 m/s classes up to 20 m/s (+ last class > 20 m/s)
                plot_edges = [0.0, 3.0, 6.0, 9.0, 12.0, 15.0, 18.0, 20.0, float("inf")]

                # group ts by station
                by_sid = {}
                for r in ts:
                    by_sid.setdefault(r["station_id"], []).append(r)
                for sid, rows in by_sid.items():
                    # frequency (percent) per sector and speed class
                    fr_long = self._freq_long_plain(rows, n_sect, plot_edges, extra_dims=None)
                    if not fr_long:
                        continue
                    # build nested: sector -> list of (vclass, pct) sorted by vclass
                    sectors = sorted({r["sector"] for r in fr_long})
                    vclasses = sorted({r["vclass"] for r in fr_long})
                    # map
                    M = {s: {vc: 0.0 for vc in vclasses} for s in sectors}
                    for r in fr_long:
                        M[r["sector"]][r["vclass"]] = r["pct"]
                    theta = [_math.radians((360.0 / n_sect) * i + (360.0 / n_sect) / 2) for i in range(n_sect)]
                    # ensure sector list matches order of theta centers
                    sectors_ordered = [round((i + 1) * (360.0 / n_sect), 6) for i in range(n_sect)]
                    # stack bars
                    try:
                        import numpy as _np  # only for zeros-like arrays; if unavailable, emulate
                        bottoms = _np.zeros(len(theta))
                    except Exception:
                        bottoms = [0.0] * len(theta)
                    fig = plt.figure(figsize=(7, 7))
                    ax = plt.subplot(111, polar=True)
                    ax.set_theta_zero_location("N"); ax.set_theta_direction(-1)
                    for vc in vclasses:
                        vals = [M[s].get(vc, 0.0) for s in sectors_ordered]
                        ax.bar(theta, vals, width=width, bottom=bottoms, align="center")
                        try:
                            bottoms = [b + v for b, v in zip(bottoms, vals)]
                        except Exception:
                            pass

                    if start_dt.year == end_dt.year:
                        period_str = f"Year {start_dt:%Y}"
                    else:
                        period_str = f"Data from {start_dt:%Y} to {end_dt:%Y}"

                    # Month and Year are displayed (since different aggregation can be applied it is not used)
                    # if start_dt.year == end_dt.year and start_dt.month == end_dt.month:
                    #     period_str = f"{start_dt:%b %Y}"
                    # else:
                    #     period_str = f"{start_dt:%b %Y} – {end_dt:%b %Y}"   
    
                    ax.set_title(f"Wind rose (frequency %) — Station: {sid}", 
                                 va="bottom", 
                                 y=1.1, 
                                 fontsize=12)
                    ax.text(
                        0.5, 1.07,                   # centered, just below the main title
                        period_str,
                        transform=ax.transAxes,
                        ha="center",
                        va="bottom",
                        fontsize=11,
                        color="0.35"
                    )

                    ax.set_rlabel_position(225)
                    # Build display labels for legend
                    # vclasses are the UPPER edges, including inf
                    legend_labels = []
                    for vc in vclasses:
                        if _math.isinf(vc):
                            legend_labels.append("> 20")
                        else:
                            legend_labels.append(f"≤ {vc:.0f}")

                    leg = ax.legend(
                        legend_labels,
                        title="Wind speed\n [m/s]",
                        loc="upper left",
                        bbox_to_anchor=(1.07, 0.7),
                        frameon=True
                    )
                    leg.get_title().set_fontsize(10)
                    
                    # ---- Station summary textbox (mean wind speed + peak wind direction) ----
                    valid_ff = [r.get("ff") for r in rows if r.get("ff") is not None]
                    mean_ws = (sum(valid_ff) / len(valid_ff)) if valid_ff else float("nan")

                    # Peak direction: sector with highest total frequency (sum across speed classes)
                    sector_sum = {}
                    for rr in fr_long:
                        s = rr.get("sector")
                        if s is None:
                            continue
                        sector_sum[s] = sector_sum.get(s, 0.0) + float(rr.get("pct", 0.0) or 0.0)

                    peak_sector = max(sector_sum, key=sector_sum.get) if sector_sum else None

                    def deg_to_compass(deg):
                        dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
                                "S","SSW","SW","WSW","W","WNW","NW","NNW"]
                        ix = int(round(deg / 22.5)) % 16
                        return dirs[ix]

                    if peak_sector is not None:
                        # sector upper edge -> approximate center angle
                        sector_width_deg = 360.0 / n_sect
                        center_deg = (peak_sector - sector_width_deg / 2.0) % 360.0
                        peak_dir_label = deg_to_compass(center_deg)
                    else:
                        peak_dir_label = "n/a"

                    stats_text = (
                        f"Mean speed: {mean_ws:.2f} m/s\n"
                        f"Peak direction: {peak_dir_label}"
                    )

                    ax.text(
                        0.95, 0.0,                      
                        stats_text,
                        transform=ax.transAxes,
                        ha="left",
                        va="bottom",
                        fontsize=10,
                        bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="0.7")
                    )


                    # ---- QWERA logo (top-left) ----
                    # Use the plugin SVG icon, rasterized via Qt to a temporary PNG.
                    try:
                        logo_svg = os.path.join(os.path.dirname(__file__), '..', "icons", "icon.svg")
                        logo_svg = os.path.abspath(logo_svg)
                        if os.path.exists(logo_svg):
                            qicon = QIcon(logo_svg)
                            pix = qicon.pixmap(270, 270)
                            img = pix.toImage()
                            tmp_logo = os.path.join(out_dir, f"{prefix}_qwera_logo_tmp.png")
                            img.save(tmp_logo, "PNG")
                            import matplotlib.image as mpimg
                            from matplotlib.offsetbox import OffsetImage, AnnotationBbox
                            logo_arr = mpimg.imread(tmp_logo)
                            oi = OffsetImage(logo_arr, zoom=0.22)
                            ab = AnnotationBbox(
                                oi, (1.22, 1.22),
                                xycoords=ax.transAxes,
                                frameon=False,
                                box_alignment=(1, 1)
                            )
                            ax.add_artist(ab)
                            # cleanup temporary logo file
                        try:
                            if tmp_logo and os.path.exists(tmp_logo):
                                os.remove(tmp_logo)
                        except Exception as e:
                            feedback.pushInfo(f"Could not delete temporary logo file: {e}")


                    except Exception as _e:
                        # If logo cannot be rendered, continue without failing the tool.
                        pass                    
                    
                    
                    fig.tight_layout()
                    out_png = os.path.join(out_dir, f"{prefix}_windrose_{sid}.png")
                    try:
                        fig.savefig(out_png, dpi=180)
                        feedback.pushInfo(f"Windrose saved: {out_png}")
                    except Exception as e:
                        feedback.reportError(f"Plot failed ({sid}): {e}")
                    finally:
                        plt.close(fig)



        feedback.pushInfo(f"Done. output folder: {out_dir}")
        return results
