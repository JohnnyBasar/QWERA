# -*- coding: utf-8 -*-
"""
Wind Frequency Matrices from Generic Table (no station ID)

- Reads a non-spatial table (e.g. CSV, Excel) already loaded in QGIS
- User selects fields for wind speed and wind direction
- Datetime field is optional:
    * if provided → monthly / seasonal / custom aggregations are available
    * if missing → only total frequencies are computed
- The whole table is treated as ONE dataset (no per-station logic)
- Calculates wind-frequency matrices (by direction sector and speed class)
- Exports speed statistics, frequency tables (long + matrix) and optional wind rose PNGs

Tested with QGIS 3.44.x (Python 3.12, Windows)
"""

from qgis.PyQt.QtCore import QCoreApplication, QDateTime, QDate
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterDefinition,
    QgsProcessingException,
    QgsVectorLayer,
    QgsFeatureRequest,
)
import os
import csv
import math
from datetime import datetime


class WindFrequencyFromTable(QgsProcessingAlgorithm):
    """
    Simple wind-frequency tool:
    - no DWD download
    - reads any attribute table in QGIS
    - no station-ID logic, whole table = one dataset
    - datetime optional
    """

    # Parameter keys
    P_INPUT_TABLE = "input_table"
    P_FIELD_SPEED = "field_speed"
    P_FIELD_DIR = "field_dir"
    P_FIELD_DATETIME = "field_datetime"

    P_SECTORS = "sectors"
    P_SPEED_BINS = "speed_bins"
    P_AUTOBIN_WIDTH = "autobin_width"

    P_FILTER_MONTHS = "filter_months"

    P_OUT_DIR = "out_dir"
    P_PLOTS = "make_plots"
    P_PREFIX = "file_prefix"

    # additional Output switches
    P_OUT_ALL_LONG = "out_all_long"
    P_OUT_ALL_MATRIX = "out_all_matrix"
    P_OUT_MONTH_LONG = "out_month_long"
    P_OUT_MONTH_MATRIX = "out_month_matrix"
    P_OUT_SEASON_LONG = "out_season_long"
    P_OUT_SEASON_MATRIX = "out_season_matrix"
    P_OUT_CUSTOM_LONG = "out_custom_long"
    P_OUT_CUSTOM_MATRIX = "out_custom_matrix"

    def icon(self):
        icon_path = os.path.join(os.path.dirname(__file__), "..", "icons", "qwera_tool_0.svg")
        return QIcon(icon_path)

    def tr(self, text):
        return QCoreApplication.translate("WindFrequencyFromTable", text)

    def createInstance(self):
        return WindFrequencyFromTable()

    def name(self):
        return "wind_frequency_from_table_simple"

    def displayName(self):
        return self.tr("Tool 0.3.0: Wind Frequency Matrices from Table")

    def group(self):
        return ("Additional Tools")

    def groupId(self):
        return "additional_tools"

    def shortHelpString(self):
        return """
            <h2>Description</h2>
            <p>
            This tool calculates <b>wind-frequency matrices</b> (by direction sector and speed class) from an input csv-table, and exports results in multiple CSV formats. 
            It supports various aggregation options such as monthly, seasonal, and user-defined “custom”  — optionally visualized as wind rose plots. The input table needs at least the following columns: wind speed, wind direction. 
            </p>

            <h2>Standards & References</h2>
            <dt><ul>
            <li><b><a href="https://www.sciencedirect.com/science/article/pii/S2215016124004576">Funk &amp; V&ouml;lker (2024)</a></b>, “A GIS-toolbox for a landscape structure based Wind Erosion Risk Assessment (WERA)” — describes the methodological context of using DWD wind statistics for erosion risk modeling.</li>
            </ul></dt>

            <h2>Inputs</h2>
            <dt><ul>
            <li><b>Input table</b>: Table with wind data. Every row should be one single wind event (hourly/daily/...).</li>
            <li><b>Wind speed (m/s)</b>: Field storing the wind speed information in meter per second.</li>            
            <li><b>Wind direction (°)</b>: Field storing the wind direction information in degrees.</li>
            <li><b>Datetime field</b>: Optional parameter for a datetime based aggregation. If empty, all data will be aggregated.</li>
            <li><b>Number of sectors</b> — Describes the number of equal sectors the direction rose will be divided in. e.g., 36 for 10° resolution. Must be between 4 and 72. Recommented is 36. </li>
            <li><b>Speed class limits</b> — optional manual bin upper limits (m/s), otherwise auto-binned. (e.g., 2,6,8,10,15, ...)</li>
            <li><b>Auto-binning step size</b> — step size (m/s) if parameter Speed class limits are not defined.</li>
            <li><b>Month filter</b> — comma-separated months (1–12) for custom aggregation. (e.g., 3,4,5, aggregates only March, April and May throughout the years)</li>
            <li><b>Group stations</b> — treat all selected stations as one (for regional averages).</li>
            <li><b>Output folder</b> — directory for all CSV and PNG results. Non-temporary directory is recommended.</li>
            <li><b>Wind rose plots</b> — optional visual output (one PNG per station).</li>
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
            <li><b>Wind rose PNGs</b> — one per station if plotting is enabled.</li>
            </ul></dt>

            <h2>Notes</h2>
            <dt><ul>
            <li>All CSVs use numeric upper bin edges for sectors and speed classes.</li>
            <li>ChatGPT was used to create this plugin.</li>
            <li>Tested with QGIS 3.44.x (Python 3.12, Windows).</li>
            </ul></dt>
        """

    # ---------- Parameter UI ----------
    def initAlgorithm(self, config=None):
        # Input table (non-spatial layer)
        p_table = QgsProcessingParameterVectorLayer(
            self.P_INPUT_TABLE,
            self.tr("Input table (non-spatial, e.g. CSV/Excel loaded in QGIS)"),
            types=[QgsProcessing.TypeVectorAnyGeometry],
        )
        self.addParameter(p_table)

        # Required fields
        p_speed = QgsProcessingParameterField(
            self.P_FIELD_SPEED,
            self.tr("Wind speed field (m/s)"),
            parentLayerParameterName=self.P_INPUT_TABLE,
        )
        self.addParameter(p_speed)

        p_dir = QgsProcessingParameterField(
            self.P_FIELD_DIR,
            self.tr("Wind direction field (degrees)"),
            parentLayerParameterName=self.P_INPUT_TABLE,
        )
        self.addParameter(p_dir)

        # Datetime field (OPTIONAL)
        p_dt = QgsProcessingParameterField(
            self.P_FIELD_DATETIME,
            self.tr("Datetime field (optional)"),
            parentLayerParameterName=self.P_INPUT_TABLE,
        )
        p_dt.setFlags(p_dt.flags() | QgsProcessingParameterDefinition.FlagOptional)
        self.addParameter(p_dt)

        # Sector & speed-class params
        self.addParameter(
            QgsProcessingParameterNumber(
                self.P_SECTORS,
                self.tr("Number of sectors (e.g. 16 → 22.5°; min: 4; max: 72)"),
                type=QgsProcessingParameterNumber.Integer,
                minValue=4,
                maxValue=72,
                defaultValue=16,
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
                self.P_AUTOBIN_WIDTH,
                self.tr("Auto-binning step size (m/s; used when classes are empty)"),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=1.0,
                minValue=0.1,
            )
        )

        p_months = QgsProcessingParameterString(
            self.P_FILTER_MONTHS,
            self.tr("Custom aggregation: filter months (comma-delimited, 1..12; empty = all)"),
            defaultValue="3,4,5",
        )
        p_months.setFlags(p_months.flags() | QgsProcessingParameterDefinition.FlagOptional)
        self.addParameter(p_months)

        # Output folder & basic options
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.P_OUT_DIR,
                self.tr("Output folder")
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.P_PLOTS,
                self.tr("Create wind rose PNG"),
                defaultValue=False,
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.P_PREFIX,
                self.tr("File prefix"),
                optional=True,
            )
        )

        # Advanced switches for which CSVs to export
        for key, label, default in [
            (self.P_OUT_ALL_LONG,   self.tr("CSV: total frequencies (long)"), False),
            (self.P_OUT_ALL_MATRIX, self.tr("CSV: total frequencies (matrix)"), True),
            (self.P_OUT_MONTH_LONG,   self.tr("CSV: monthly frequencies (long)"), False),
            (self.P_OUT_MONTH_MATRIX, self.tr("CSV: monthly frequencies (matrix)"), False),
            (self.P_OUT_SEASON_LONG,   self.tr("CSV: seasonal frequencies (long)"), False),
            (self.P_OUT_SEASON_MATRIX, self.tr("CSV: seasonal frequencies (matrix)"), False),
            (self.P_OUT_CUSTOM_LONG,   self.tr("CSV: custom frequencies (long)"), False),
            (self.P_OUT_CUSTOM_MATRIX, self.tr("CSV: custom frequencies (matrix)"), True),
        ]:
            p = QgsProcessingParameterBoolean(key, label, defaultValue=default)
            p.setFlags(p.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
            self.addParameter(p)

    # ---------- Helpers ----------
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
            for t in month_str.split(","):
                t = t.strip()
                if t:
                    m = int(t)
                    if 1 <= m <= 12:
                        months.append(m)
        return sorted(set(months))

    @staticmethod
    def _percentile_inc(values, p: float):
        """Inclusive percentile (linear interpolation), p in [0,1]."""
        if not values:
            return None
        data = sorted(values)
        n = len(data)
        if n == 1:
            return float(data[0])
        rank = p * (n - 1)
        lo = int(rank)
        hi = min(lo + 1, n - 1)
        frac = rank - lo
        return float(data[lo] * (1 - frac) + data[hi] * frac)

    @staticmethod
    def _write_csv(path, header, rows):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            # Use semicolon as delimiter (German locale-friendly)
            w = csv.writer(f, delimiter=";")
            w.writerow(header)
            for r in rows:
                w.writerow(r)

    @staticmethod
    def _sector_upper(dd, n_sect):
        """Return sector upper edge in degrees for a given direction dd in [0,360)."""
        if dd < 0 or dd >= 360:
            dd = dd % 360.0
        width = 360.0 / n_sect
        # 0° belongs to first bin [0, width)
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
        return edges[-1]

    @staticmethod
    def _freq_long_plain(rows, n_sect, edges, extra_dims=None):
        """
        rows: list of dicts with keys: ff, dd, plus optional extra_dims like 'month', 'season'
        Returns list of dicts: {extra_dims..., sector, vclass, n, pct}
        """
        counts = {}
        totals = {}
        extra_dims = extra_dims or []

        for r in rows:
            ff = r["ff"]
            dd = r["dd"]
            if ff is None or dd is None:
                continue
            if ff < 0:
                continue
            dd = dd % 360.0
            sec_up = WindFrequencyFromTable._sector_upper(dd, n_sect)
            v_up = WindFrequencyFromTable._vclass_upper(ff, edges)

            if extra_dims:
                key_extra = tuple(r.get(dim) for dim in extra_dims)
            else:
                key_extra = ()

            totals[key_extra] = totals.get(key_extra, 0) + 1
            key = (key_extra, sec_up, v_up)
            counts[key] = counts.get(key, 0) + 1

        out = []
        for (key_extra, sec_up, v_up), n in counts.items():
            total = totals.get(key_extra, 0) or 1
            pct = round(100.0 * n / total, 6)
            rec = {}
            for i, dim in enumerate(extra_dims):
                rec[dim] = key_extra[i]
            rec.update({"sector": sec_up, "vclass": v_up, "n": n, "pct": pct})
            out.append(rec)
        return out

    @staticmethod
    def _freq_matrix_from_long_plain(long_rows, extra_dims=None, value_col="n"):
        """
        Convert long rows to matrix-like flat table.
        Rows grouped by extra_dims + vclass; columns are sector upper edges.
        Returns (header, rows) ready for CSV.
        """
        extra_dims = extra_dims or []
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

    @staticmethod
    def _parse_datetime_value(val, feedback):
        """Try to convert various QGIS field types / strings to Python datetime."""
        if val is None:
            return None

        # QDateTime
        if isinstance(val, QDateTime):
            return val.toPyDateTime()

        # QDate
        if isinstance(val, QDate):
            return datetime(val.year(), val.month(), val.day(), 0, 0, 0)

        # Already a datetime
        if isinstance(val, datetime):
            return val

        # Fallback: parse string with several common formats
        s = str(val).strip()
        if not s:
            return None

        # Try ISO first
        try:
            return datetime.fromisoformat(s)
        except Exception:
            pass

        # A few common patterns
        fmts = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%d.%m.%Y %H:%M:%S",
            "%d.%m.%Y %H:%M",
            "%d.%m.%Y",
        ]
        for fmt in fmts:
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                continue

        feedback.reportError(f"Could not parse datetime value: '{s}'")
        return None
    

    @staticmethod
    def _plot_windrose_png(rows, n_sect, out_png, feedback, period_str=None, title=None, out_dir=None, prefix=None):
        import math as _math
        import matplotlib.pyplot as plt

        # fixed classes for plotting (as in DWD tool)
        plot_edges = [0.0, 3.0, 6.0, 9.0, 12.0, 15.0, 18.0, 20.0, float("inf")]
        fr_long = WindFrequencyFromTable._freq_long_plain(rows, n_sect, plot_edges, extra_dims=None)
        if not fr_long:
            return

        width = 2 * _math.pi / n_sect
        sectors = sorted({r["sector"] for r in fr_long})
        vclasses = sorted({r["vclass"] for r in fr_long})

        M = {s: {vc: 0.0 for vc in vclasses} for s in sectors}
        for r in fr_long:
            M[r["sector"]][r["vclass"]] = r["pct"]

        theta = [_math.radians((360.0 / n_sect) * i + (360.0 / n_sect) / 2) for i in range(n_sect)]
        sectors_ordered = [round((i + 1) * (360.0 / n_sect), 6) for i in range(n_sect)]

        try:
            import numpy as _np
            bottoms = _np.zeros(len(theta))
        except Exception:
            bottoms = [0.0] * len(theta)

        fig = plt.figure(figsize=(7, 7))
        ax = plt.subplot(111, polar=True)
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)

        for vc in vclasses:
            vals = [M[s].get(vc, 0.0) for s in sectors_ordered]
            ax.bar(theta, vals, width=width, bottom=bottoms, align="center")
            try:
                bottoms = [b + v for b, v in zip(bottoms, vals)]
            except Exception:
                pass

        ax.set_title(title or "Wind rose (frequency %) — full dataset", va="bottom", y=1.10, fontsize=12)

        if period_str:
            ax.text(
                0.5, 1.07, period_str,
                transform=ax.transAxes, ha="center", va="bottom",
                fontsize=11, color="0.35"
            )

        ax.set_rlabel_position(225)

        # legend labels (≤ upper edge; last class > 20)
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

        # stats box: mean speed + peak direction
        valid_ff = [r.get("ff") for r in rows if r.get("ff") is not None]
        mean_ws = (sum(valid_ff) / len(valid_ff)) if valid_ff else float("nan")

        sector_sum = {}
        for rr in fr_long:
            s = rr.get("sector")
            sector_sum[s] = sector_sum.get(s, 0.0) + float(rr.get("pct", 0.0) or 0.0)
        peak_sector = max(sector_sum, key=sector_sum.get) if sector_sum else None

        def deg_to_compass(deg):
            dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
            ix = int(round(deg / 22.5)) % 16
            return dirs[ix]

        if peak_sector is not None:
            sector_width_deg = 360.0 / n_sect
            center_deg = (peak_sector - sector_width_deg / 2.0) % 360.0
            peak_dir_label = deg_to_compass(center_deg)
        else:
            peak_dir_label = "n/a"

        stats_text = f"Mean speed: {mean_ws:.2f} m/s\nPeak direction: {peak_dir_label}"
        ax.text(
            0.95, 0.0, stats_text,
            transform=ax.transAxes, ha="left", va="bottom", fontsize=10,
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="0.7")
        )

        # optional logo (Qt rasterize SVG → temp PNG)
        tmp_logo = None
        try:
            from qgis.PyQt.QtGui import QIcon
            logo_svg = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "icons", "icon.svg"))
            if os.path.exists(logo_svg) and out_dir:
                qicon = QIcon(logo_svg)
                pix = qicon.pixmap(270, 270)
                img = pix.toImage()
                tmp_logo = os.path.join(out_dir, f"{prefix or 'wind'}_qwera_logo_tmp.png")
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
        except Exception:
            pass
        finally:
            try:
                if tmp_logo and os.path.exists(tmp_logo):
                    os.remove(tmp_logo)
            except Exception as e:
                feedback.pushInfo(f"Could not delete temporary logo file: {e}")

        fig.tight_layout()
        fig.savefig(out_png, dpi=180)
        plt.close(fig)

    # ---------- Main ----------
    def processAlgorithm(self, parameters, context, feedback):
        # Input table
        vl = self.parameterAsVectorLayer(parameters, self.P_INPUT_TABLE, context)
        if not isinstance(vl, QgsVectorLayer):
            raise QgsProcessingException("Input table is not a valid vector/table layer.")

        field_speed = self.parameterAsString(parameters, self.P_FIELD_SPEED, context)
        field_dir = self.parameterAsString(parameters, self.P_FIELD_DIR, context)
        field_dt = self.parameterAsString(parameters, self.P_FIELD_DATETIME, context)

        have_dt = bool(field_dt)

        # Require only speed & direction; datetime is optional
        if not field_speed or not field_dir:
            raise QgsProcessingException(
                "Please select at least wind speed and wind direction fields.\n"
                "Datetime field is optional."
            )

        n_sect = int(self.parameterAsInt(parameters, self.P_SECTORS, context))

        speed_bins_raw = self.parameterAsString(parameters, self.P_SPEED_BINS, context)
        speed_bins_str = (speed_bins_raw or "").strip()
        autobin_width = float(self.parameterAsDouble(parameters, self.P_AUTOBIN_WIDTH, context))

        filter_months_raw = self.parameterAsString(parameters, self.P_FILTER_MONTHS, context)
        filter_months = self._parse_month_list(filter_months_raw)

        make_plots = self.parameterAsBool(parameters, self.P_PLOTS, context)
        prefix_in = (self.parameterAsString(parameters, self.P_PREFIX, context) or "").strip()
        prefix = prefix_in or "wind_frequency_table"

        out_dir_in = self.parameterAsString(parameters, self.P_OUT_DIR, context)
        if not out_dir_in or out_dir_in.upper() == "TEMPORARY_OUTPUT":
            out_dir = os.path.join(os.path.expanduser("~"), "wind_frequency_output")
            feedback.pushInfo(f"Using default output folder: {out_dir}")
        else:
            out_dir = out_dir_in
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        # Output switches
        want_all_long   = self.parameterAsBool(parameters, self.P_OUT_ALL_LONG, context)
        want_all_matrix = self.parameterAsBool(parameters, self.P_OUT_ALL_MATRIX, context)
        want_mon_long   = self.parameterAsBool(parameters, self.P_OUT_MONTH_LONG, context)
        want_mon_matrix = self.parameterAsBool(parameters, self.P_OUT_MONTH_MATRIX, context)
        want_sea_long   = self.parameterAsBool(parameters, self.P_OUT_SEASON_LONG, context)
        want_sea_matrix = self.parameterAsBool(parameters, self.P_OUT_SEASON_MATRIX, context)
        want_cus_long   = self.parameterAsBool(parameters, self.P_OUT_CUSTOM_LONG, context)
        want_cus_matrix = self.parameterAsBool(parameters, self.P_OUT_CUSTOM_MATRIX, context)

        # If there is no datetime field, disable all date-based outputs
        if not have_dt and (want_mon_long or want_mon_matrix or
                            want_sea_long or want_sea_matrix or
                            want_cus_long or want_cus_matrix):
            feedback.pushInfo(
                "No datetime field selected → skipping monthly, seasonal and custom-month outputs."
            )
            want_mon_long = want_mon_matrix = False
            want_sea_long = want_sea_matrix = False
            want_cus_long = want_cus_matrix = False

        # ---- Build time series (ts) from table ----
        ts = []
        feats = vl.getFeatures(QgsFeatureRequest())
        total_feats = vl.featureCount() or 0
        processed = 0

        feedback.pushInfo("Reading table and building time series …")

        for f in feats:
            processed += 1
            if total_feats and processed % 1000 == 0:
                feedback.setProgress(int(100.0 * processed / total_feats))

            # Datetime (optional)
            if have_dt:
                dt_val = f[field_dt]
                dt = self._parse_datetime_value(dt_val, feedback)
                if dt is None:
                    continue
            else:
                dt = None

            # Speed
            try:
                ff_val = f[field_speed]
                ff = float(ff_val) if ff_val is not None else None
            except Exception:
                ff = None

            # Direction
            try:
                dd_val = f[field_dir]
                dd = float(dd_val) if dd_val is not None else None
            except Exception:
                dd = None

            if ff is None or dd is None:
                continue
            if ff < 0:
                continue

            rec = {
                "ff": float(ff),
                "dd": float(dd % 360.0),
            }
            if have_dt:
                rec["date"] = dt

            ts.append(rec)

        if not ts:
            raise QgsProcessingException(
                "No valid (speed + direction [+ datetime]) rows after cleaning input table."
            )

        # Sort (if we have dates, sort by them; otherwise sort by speed for determinism)
        if have_dt:
            ts.sort(key=lambda x: x["date"])
        else:
            ts.sort(key=lambda x: x["ff"])

        # ---- Speed-info (overall only) ----
        from statistics import mean

        all_vals = [r["ff"] for r in ts]
        if not all_vals:
            raise QgsProcessingException("No valid speed values found in the input table.")

        overall_row = [
            "__ALL__",
            len(all_vals),
            float(min(all_vals)),
            float(mean(all_vals)),
            float(max(all_vals)),
            WindFrequencyFromTable._percentile_inc(all_vals, 0.90),
            WindFrequencyFromTable._percentile_inc(all_vals, 0.95),
        ]
        speed_rows = [overall_row]

        out_speed_info = os.path.join(out_dir, f"{prefix}_speed_info.csv")
        self._write_csv(
            out_speed_info,
            ["id", "n", "ff_min", "ff_mean", "ff_max", "ff_p90", "ff_p95"],
            speed_rows,
        )
        feedback.pushInfo(f"Speed-info written: {out_speed_info}")

        # ---- Determine speed-class edges ----
        edges = self._parse_speed_bins(speed_bins_str)
        if edges:
            feedback.pushInfo(f"Using manual speed-class limits: {edges} (+∞)")
        else:
            if autobin_width <= 0:
                raise QgsProcessingException(
                    "Auto-binning: step size must be > 0 or specify classes manually."
                )
            gmax = max((r["ff"] for r in ts), default=0.0)
            top = math.ceil(gmax / autobin_width) * autobin_width
            edges = [0.0]
            x = 0.0
            while x < top - 1e-12:
                x = round(x + autobin_width, 6)
                edges.append(x)
            feedback.pushInfo(
                f"Auto-binning: step={autobin_width} m/s, edges 0..{top} → {edges} (+∞)"
            )
        if not math.isinf(edges[-1]):
            edges = edges + [float("inf")]

        # ---- Annotate month/season if we have datetime ----
        if have_dt:
            for r in ts:
                m = r["date"].month
                r["month"] = m
                r["season"] = (
                    "DJF"
                    if m in (12, 1, 2)
                    else ("MAM" if m in (3, 4, 5) else ("JJA" if m in (6, 7, 8) else "SON"))
                )

        results = {"OUT_DIR": out_dir, "SPEED_INFO_CSV": out_speed_info}

        # ---- 1) Total (entire dataset) ----
        if want_all_long or want_all_matrix:
            feedback.pushInfo("Aggregate frequencies (total dataset) …")
            long_all = self._freq_long_plain(ts, n_sect, edges, extra_dims=None)
            if want_all_long:
                out_all_long = os.path.join(out_dir, f"{prefix}_frequency_total.csv")
                header = ["sector", "vclass", "n", "pct"]
                rows = [
                    [r["sector"], r["vclass"], r["n"], r["pct"]]
                    for r in long_all
                ]
                self._write_csv(out_all_long, header, rows)
                results["CSV_ALL"] = out_all_long
            if want_all_matrix:
                header, rows = self._freq_matrix_from_long_plain(
                    long_all, extra_dims=[], value_col="n"
                )
                # header: ["vclass", sector1, sector2, ...]
                out_all_mat = os.path.join(out_dir, f"{prefix}_matrix_total.csv")
                self._write_csv(out_all_mat, header, rows)
                results["CSV_ALL_MATRIX"] = out_all_mat

        # ---- 2) Monthly ----
        if have_dt and (want_mon_long or want_mon_matrix):
            feedback.pushInfo("Aggregate frequencies (monthly) …")
            long_mon = self._freq_long_plain(ts, n_sect, edges, extra_dims=["month"])
            if want_mon_long:
                out_mon_long = os.path.join(out_dir, f"{prefix}_frequency_by_month.csv")
                header = ["month", "sector", "vclass", "n", "pct"]
                rows = [
                    [r["month"], r["sector"], r["vclass"], r["n"], r["pct"]]
                    for r in long_mon
                ]
                self._write_csv(out_mon_long, header, rows)
                results["CSV_MONTH"] = out_mon_long
            if want_mon_matrix:
                header, rows = self._freq_matrix_from_long_plain(
                    long_mon, extra_dims=["month"], value_col="n"
                )
                out_mon_mat = os.path.join(out_dir, f"{prefix}_matrix_by_month.csv")
                self._write_csv(out_mon_mat, header, rows)
                results["CSV_MONTH_MATRIX"] = out_mon_mat

        # ---- 3) Seasonal ----
        if have_dt and (want_sea_long or want_sea_matrix):
            feedback.pushInfo("Aggregate frequencies (seasonal) …")
            long_sea = self._freq_long_plain(ts, n_sect, edges, extra_dims=["season"])
            if want_sea_long:
                out_sea_long = os.path.join(out_dir, f"{prefix}_frequency_by_season.csv")
                header = ["season", "sector", "vclass", "n", "pct"]
                rows = [
                    [r["season"], r["sector"], r["vclass"], r["n"], r["pct"]]
                    for r in long_sea
                ]
                self._write_csv(out_sea_long, header, rows)
                results["CSV_SEASON"] = out_sea_long
            if want_sea_matrix:
                header, rows = self._freq_matrix_from_long_plain(
                    long_sea, extra_dims=["season"], value_col="n"
                )
                out_sea_mat = os.path.join(out_dir, f"{prefix}_matrix_by_season.csv")
                self._write_csv(out_sea_mat, header, rows)
                results["CSV_SEASON_MATRIX"] = out_sea_mat

        # ---- 4) Custom: filter months ----
        if have_dt and (want_cus_long or want_cus_matrix):
            if filter_months:
                feedback.pushInfo(f"Custom output: filter months {filter_months} …")
                ts_custom = [r for r in ts if r["month"] in filter_months]
            else:
                ts_custom = list(ts)

            if not ts_custom:
                feedback.pushInfo("Custom output: no data in filter – skip.")
            else:
                long_cus = self._freq_long_plain(
                    ts_custom,
                    n_sect,
                    edges,
                    extra_dims=None,  # just one dataset
                )

                mon_label = "all" if not filter_months else "_".join(
                    [f"{m:02d}" for m in filter_months]
                )

                if want_cus_long:
                    out_cus_long = os.path.join(
                        out_dir,
                        f"{prefix}_frequency_custom_m{mon_label}.csv",
                    )
                    header = ["sector", "vclass", "n", "pct"]
                    rows = [
                        [r["sector"], r["vclass"], r["n"], r["pct"]]
                        for r in long_cus
                    ]
                    self._write_csv(out_cus_long, header, rows)
                    results["CSV_CUSTOM"] = out_cus_long

                if want_cus_matrix:
                    header, rows = self._freq_matrix_from_long_plain(
                        long_cus,
                        extra_dims=[],  # only vclass + sectors
                        value_col="n",
                    )
                    out_cus_mat = os.path.join(
                        out_dir,
                        f"{prefix}_matrix_custom_m{mon_label}_FOR_WIND_STAT_TOOL.csv",
                    )
                    self._write_csv(out_cus_mat, header, rows)
                    results["CSV_CUSTOM_MATRIX"] = out_cus_mat

        # ---- Optional wind-rose PNG ----
        if make_plots:
            try:
                import matplotlib.pyplot as plt  # just to test availability
            except Exception as e:
                feedback.reportError(f"Matplotlib not available – skipping wind-rose plot: {e}")
            else:
                period_str = None
                if have_dt:
                    d0 = min(r["date"] for r in ts)
                    d1 = max(r["date"] for r in ts)
                    if d0.year == d1.year:
                        period_str = f"Year {d0:%Y}"
                    else:
                        period_str = f"Data from {d0:%Y} to {d1:%Y}"

                out_png = os.path.join(out_dir, f"{prefix}_windrose.png")
                self._plot_windrose_png(
                    ts, n_sect,
                    out_png=out_png,
                    feedback=feedback,
                    period_str=period_str,
                    title="Wind rose (frequency %) — full dataset",
                    out_dir=out_dir,
                    prefix=prefix,
                )
                feedback.pushInfo(f"Wind-rose saved: {out_png}")


        feedback.pushInfo(f"Done. Output folder: {out_dir}")
        return results