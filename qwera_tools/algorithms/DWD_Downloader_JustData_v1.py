# -*- coding: utf-8 -*-
"""
Tool: DWD – Downloader (Data Only) with Resolution Selection & Dry-Run
Pandas/Polars free version — uses only wetterdienst + Python stdlib.

Outputs (unchanged in spirit):
- Summary CSV (always)
- Raw timeseries (combined) CSV (optional)
- Raw timeseries per-station CSVs (optional)
- Speed-info CSV with min/mean/max/P90/P95 per station + overall (optional)

Tested with: QGIS 3.44.x (Python 3.12, Windows)
"""

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing, QgsProcessingAlgorithm,
    QgsProcessingParameterVectorLayer, QgsProcessingParameterField,
    QgsProcessingParameterString, QgsProcessingParameterDateTime,
    QgsProcessingParameterBoolean, QgsProcessingParameterFolderDestination,
    QgsProcessingParameterEnum, QgsProcessingParameterDefinition,
    QgsProcessingException, QgsVectorLayer, QgsFeatureRequest, QgsApplication
)

import os, tempfile, csv
from statistics import mean
from datetime import datetime
try:
    from . import dwd_cdc
except Exception:
    import dwd_cdc


class DwdWindDownloader(QgsProcessingAlgorithm):
    # Parameter keys
    P_STATION_LAYER      = "station_layer"
    P_STATION_ID_FIELD   = "station_id_field"
    P_USE_SELECTION      = "use_selection"
    P_STATIONS           = "stations"
    P_START              = "start"
    P_END                = "end"
    P_RESOLUTION         = "resolution"
    P_WIND_MODE = "wind_mode"
    P_DRYRUN             = "dry_run"
    P_OUT_DIR            = "out_dir"
    P_EXPORT_RAW         = "export_raw"
    P_EXPORT_RAW_SPLIT   = "export_raw_split"
    P_PREFIX             = "file_prefix"

    # Output keys
    O_SUMMARY_CSV        = "SUMMARY_CSV"
    O_RAW_CSV            = "RAW_CSV"
    O_RAW_CSV_DIR        = "RAW_CSV_DIR"
    O_RAW_CSV_LIST       = "RAW_CSV_LIST"
    O_SPEED_INFO         = "SPEED_INFO_CSV"
    O_OUT_DIR            = "OUT_DIR"

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
        return QCoreApplication.translate("DwdWindDownloader", text)

    def createInstance(self):
        return DwdWindDownloader()

    def name(self):
        return "dwd_downloader_only"

    def displayName(self):
        return self.tr("DWD – Downloader (just Data)")

    def group(self):
        return "Additional Tools"

    def groupId(self):
        return "additional_tools"

    def shortHelpString(self):
        return """
            <h2>Description</h2>
            <p>
            This tool downloads <b>wind data</b> from the <b>Deutscher Wetterdienst (DWD)</b> for selected weather stations and given filter options and saves the results as CSV files. It can either perform a full download or a dry-run check of data availability.
            Filter option include temporal resolution, time period and wind mode (max or mean wind speed).       
            </p>

            <h2>Standards & References</h2>
            <dt><ul>
            <li><b><a href="https://www.dwd.de/EN/Home/home_node.html">Deutscher Wetterdienst (DWD) Open Data</a></b> — official source of meteorological observations in Germany.</li>
            <li><b><a href="https://pypi.org/project/wetterdienst/">Wetterdienst Python package</a></b> — used for automated data requests from the DWD Observation API.</li>
            <li><b><a href="https://www.sciencedirect.com/science/article/pii/S2215016124004576">Funk &amp; V&ouml;lker (2024)</a></b>, “A GIS-toolbox for a landscape structure based Wind Erosion Risk Assessment (WERA)” — provides the broader methodological framework in which this downloader supports wind statistics for WERA modules.</li>
            </ul></dt>
         

            <h2>Inputs</h2>
            <dt><ul>
            <li><b>Station layer (optional)</b> — vector layer with station IDs in a chosen field.</li>
            <li><b>Station ID field</b> — the attribute field containing the DWD station identifier.</li>
            <li><b>Manual station IDs</b> — comma-separated list of IDs (e.g. 04036, 05084).</li>
            <li><b>Start / End date</b> — UTC time range for data download.</li>
            <li><b>Temporal resolution</b> — 10-minute, hourly, daily, or monthly.</li>
            <li><b>Wind mode</b> — Either “mean wind speed” or “maximum wind gust” can be selected. If “maximum wind gust” has been selected it overwrites the Temporal resolution since wind gust data is only available for the 10-minute resolution.</li>
            <li><b>Dry-Run (optional)</b> — check availability without downloading data.</li>
            <li><b>Output folder</b> — directory for saving CSV outputs. It is recommended not to use a temporary directory.</li>
            <li><b>Export options</b> — toggle for combined and/or per-station raw-data exports.</li>
            <li><b>File prefix</b> — optional custom prefix for output filenames.</li>
            </ul></dt>

            <h2>Outputs</h2>
            <dt><ul>
            <li><b>Summary CSV</b> — always created; includes station_id, n_records, first_date, last_date, resolution.</li>
            <li><b>Raw data CSV</b> — single file containing all stations (optional).</li>
            <li><b>Per-station CSVs</b> — one file per station (optional).</li>
            <li><b>Speed info CSV</b> — summary of wind-speed statistics per station and overall.</li>
            </ul></dt>

            <h2>Notes</h2>
            <dt><ul>
            <li>Not all stations provide data for all temporal resolutions or time periods.</li>
            <li>Requires internet access.</li>
            <li>ChatGPT was used to create this plugin.</li>
            <li>Tested with QGIS 3.44.x (Python 3.12, Windows).</li>
            </ul></dt>

        """

    # ---------- Light deps: only  ----------
  
    # Aktuell nicht gebraucht
    # @staticmethod
    # def _get(d, *keys, default=None):
    #     for k in keys:
    #         if k in d and d[k] is not None:
    #             return d[k]
    #     return default


    @staticmethod
    def _iso(dt: datetime | None) -> str:
        return dt.isoformat() if isinstance(dt, datetime) else ""

    
    # ---------- UI/Parameter ----------
    def initAlgorithm(self, config=None):
        p_layer = QgsProcessingParameterVectorLayer(
            self.P_STATION_LAYER, self.tr("Station-Layer"),
            types=[QgsProcessing.TypeVectorPoint]
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
            QgsProcessingParameterDateTime(
                self.P_START, self.tr("Start date (UTC)"),
                type=QgsProcessingParameterDateTime.DateTime
            )
        )
        self.addParameter(
            QgsProcessingParameterDateTime(
                self.P_END, self.tr("End date (UTC)"),
                type=QgsProcessingParameterDateTime.DateTime
            )
        )

        self.addParameter(
            QgsProcessingParameterEnum(
                self.P_RESOLUTION, self.tr("Temporal resolution"),
                options=self.RES_LABELS, allowMultiple=False, defaultValue=1  # hourly
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
            QgsProcessingParameterBoolean(
                self.P_DRYRUN,
                self.tr("Check only (dry run): Count availability, do not save raw data"),
                defaultValue=False
            )
        )

        self.addParameter(
            QgsProcessingParameterFolderDestination(self.P_OUT_DIR, self.tr("Output folder (not TEMPORARY_OUTPUT)"))
        )

        self.addParameter(
            QgsProcessingParameterBoolean(self.P_EXPORT_RAW, self.tr("Export raw data (a CSV file)"), defaultValue=True)
        )
        self.addParameter(
            QgsProcessingParameterBoolean(self.P_EXPORT_RAW_SPLIT, self.tr("Export raw data for each station"), defaultValue=True)
        )
        self.addParameter(
            QgsProcessingParameterString(self.P_PREFIX, self.tr("File prefix (optional)"), optional=True)
        )

    # ---------- Main ----------
    def processAlgorithm(self, parameters, context, feedback):

        # Inputs
        vl         = self.parameterAsVectorLayer(parameters, self.P_STATION_LAYER, context)
        id_field   = self.parameterAsString(parameters, self.P_STATION_ID_FIELD, context)
        use_sel    = self.parameterAsBool(parameters, self.P_USE_SELECTION, context)

        manual_raw = self.parameterAsString(parameters, self.P_STATIONS, context)
        manual_ids = [x.strip() for x in (manual_raw or "").split(",") if x and x.strip()]
        manual_ids = [(i.zfill(5) if i.isdigit() else i) for i in manual_ids]

        layer_ids  = dwd_cdc.station_ids_from_layer(vl, id_field, use_sel, feedback) if vl else []
        stations   = sorted(set(layer_ids) | set(manual_ids))
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
        use_max_wind = (wind_mode == 1)  # or whatever index "maximum wind" has
        if use_max_wind:
            if res_key != "minute_10":
                feedback.pushInfo("Maximum wind speed (gust) requires 10-minute resolution. Forcing to 'minute_10'.")
            res_key = "minute_10"

        dry_run  = self.parameterAsBool(parameters, self.P_DRYRUN, context)


        export_raw_combined = self.parameterAsBool(parameters, self.P_EXPORT_RAW, context)
        export_raw_split    = self.parameterAsBool(parameters, self.P_EXPORT_RAW_SPLIT, context)
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

        # DWD query
         # ---- DWD aus CDC laden (ohne wetterdienst) ----
        feedback.pushInfo(
            f"CDC: Loading {self.RES_LABELS[res_idx]} data for "
            f"{len(stations)} station(s): {', '.join(stations[:10])}."
        )

        try:
            timeseries = dwd_cdc.get_wind_timeseries_from_cdc(
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

        if not timeseries:
            raise QgsProcessingException(
                "No valid (speed+direction) pairs after CDC download.\n"
                "- Check time window (start < end; try a longer period)\n"
                "- Check station IDs (5 digits, e.g., 04036)\n"
                "- Selected resolution may not be available for the station/time period."
            )

        # sort by station/date
        timeseries.sort(key=lambda x: (x["station_id"], x["date"]))

        # --- Summary (always) ---
        present_sids = []
        summary_rows = []
        # group by station
        i = 0
        n = len(timeseries)
        while i < n:
            sid = timeseries[i]["station_id"]
            j = i
            dates = []
            while j < n and timeseries[j]["station_id"] == sid:
                dates.append(timeseries[j]["date"])
                j += 1
            present_sids.append(sid)
            first_date = min(dates) if dates else None
            last_date  = max(dates) if dates else None
            summary_rows.append([
                sid,
                len(dates),
                self._iso(first_date),
                self._iso(last_date),
                res_key
            ])
            i = j

        # add missing stations (0 records)
        missing = [s for s in stations if s not in set(present_sids)]
        for sid in missing:
            summary_rows.append([sid, 0, "", "", res_key])

        summary_rows.sort(key=lambda r: r[0])
        out_summary = os.path.join(out_dir, f"{prefix}_summary_{res_key}.csv")
        dwd_cdc.write_csv(
                out_summary,
                ["station_id", "n_records", "first_date", "last_date", "resolution"],
                summary_rows,
                self.CSV_DELIM,
            )
        feedback.pushInfo(f"Summary written: {out_summary}")
        feedback.pushInfo(f"Stations with data: {len(present_sids)}/{len(stations)} | No results: {len(missing)}")

        results = {self.O_SUMMARY_CSV: out_summary, self.O_OUT_DIR: out_dir}

        if dry_run:
            feedback.pushInfo("Dry run enabled: no raw data / speed information exported.")
            return results

        # --- Speed-Info per station + overall ---
        # collect speeds per station
        speeds_by_sid = {}
        for row in timeseries:
            speeds_by_sid.setdefault(row["station_id"], []).append(row["ff"])

        speed_rows = []
        for sid, vals in speeds_by_sid.items():
            if not vals:
                continue
            speed_rows.append([
                sid,
                len(vals),
                float(min(vals)),
                float(mean(vals)),
                float(max(vals)),
                dwd_cdc.percentile_inc(vals, 0.90),
                dwd_cdc.percentile_inc(vals, 0.95),
            ])

        # overall
        all_vals = [r["ff"] for r in timeseries]
        overall_row = [
            "__ALL__",
            len(all_vals),
            float(min(all_vals)) if all_vals else "",
            float(mean(all_vals)) if all_vals else "",
            float(max(all_vals)) if all_vals else "",
            dwd_cdc.percentile_inc(all_vals, 0.90),
            dwd_cdc.percentile_inc(all_vals, 0.95),
        ]
        speed_rows.append(overall_row)

        out_speed_info = os.path.join(out_dir, f"{prefix}_speed_info.csv")
        dwd_cdc.write_csv(
                out_speed_info,
                ["station_id", "n", "ff_min", "ff_mean", "ff_max", "ff_p90", "ff_p95"],
                speed_rows,
                self.CSV_DELIM,
            )
        feedback.pushInfo(f"Speed-Info written: {out_speed_info}")
        results[self.O_SPEED_INFO] = out_speed_info

        # --- Raw exports ---
        if export_raw_combined:
            combined_rows = []
            for r in timeseries:
                combined_rows.append({
                    "station_id": r["station_id"],
                    "date": self._iso(r["date"]),
                    "w_speed": r["ff"],
                    "w_dir": r["dd"],
                    "qn_speed": r.get("qn_ff", ""),
                    "qn_dir": r.get("qn_dd", ""),
                })

            raw_path = os.path.join(out_dir, f"{prefix}_raw_timeseries.csv")
            dwd_cdc.write_csv(
                raw_path,
                ["station_id", "date", "w_speed", "w_dir", "qn_speed", "qn_dir"],
                combined_rows,
                self.CSV_DELIM,
            )

            feedback.pushInfo(f"Raw data (one file) written: {raw_path}")
            results[self.O_RAW_CSV] = raw_path

        if export_raw_split:
            raw_dir = os.path.join(out_dir, f"{prefix}_raw_by_station")
            os.makedirs(raw_dir, exist_ok=True)
            file_list = []
            # iterate grouped by station (timeseries is sorted)
            i = 0
            n = len(timeseries)
            while i < n:
                sid = timeseries[i]["station_id"]
                j = i
                rows = []
                while j < n and timeseries[j]["station_id"] == sid:
                    r = timeseries[j]
                    rows.append({
                        "station_id": sid,
                        "date": self._iso(r["date"]),
                        "w_speed": r["ff"],
                        "w_dir": r["dd"],
                        "qn_speed": r.get("qn_ff", ""),
                        "qn_dir": r.get("qn_dd", ""),
                    })
                    j += 1

                fpath = os.path.join(raw_dir, f"{prefix}_raw_{sid}.csv")
                dwd_cdc.write_csv(
                    fpath,
                    ["station_id", "date", "w_speed", "w_dir", "qn_speed", "qn_dir"],
                    rows,
                    self.CSV_DELIM,
                )
                file_list.append(fpath)
                i = j
            feedback.pushInfo(f"Raw data per station written in: {raw_dir} ({len(file_list)} files)")
            results[self.O_RAW_CSV_DIR]  = raw_dir
            results[self.O_RAW_CSV_LIST] = ";".join(file_list)

        feedback.pushInfo(f"Done. Output directory: {out_dir}")
        return results
