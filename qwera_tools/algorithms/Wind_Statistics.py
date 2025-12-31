# -*- coding: utf-8 -*-
"""
TOOL X: Wind statistics & shadow parameters
- Input: custom aggregation CSV from
  "DWD – Downloader and Wind Frequency Matrices Creator"
  (vclass;45;90;135;180;225;270;315;360;…)
- Output: WERA-style CSV with
  (Record, Bez, Azimut, Altitude, Constant)
  to be used as input for:
  TOOL 2: Wind Shade Calculator (QWERA, Funk & Völker 2024, Modul 2)
"""

import os
import csv
import math
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterFile,
    QgsProcessingParameterNumber,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterBoolean,
    QgsProcessingException,
)


class WIND_STATS(QgsProcessingAlgorithm):
    """
    Wind statistics & shadow parameter calculator
    """

    PARAM_INPUT_CSV = "INPUT_CSV"
    PARAM_THRESHOLD = "THRESHOLD"
    PARAM_POROSITY = "POROSITY"
    PARAM_DROP_EMPTY = "DROP_EMPTY_DIRECTIONS"
    PARAM_OUTPUT = "OUTPUT"

    def icon(self):
        icon_path = os.path.join(os.path.dirname(__file__), "..", "icons", "qwera_tool_0.svg")
        return QIcon(icon_path)
    
    def tr(self, string):
        return QCoreApplication.translate("QWERA", string)

    def createInstance(self):
        return WIND_STATS()

    def name(self):
        return "qwera_wind_statistics"

    def displayName(self):
        return self.tr("Tool 0.4.0: Wind Shadow Parameters")

    def group(self):
        return "Additional Tools"

    def groupId(self):
        return "additional_tools"

    def shortHelpString(self):
        return """
            <h2>Description</h2>
            <p>
            This tool processes a <b>custom aggregated wind matrix</b> from the QWERA <i>DWD – Downloader and Wind Frequency Matrices Creator</i> - Tool or the <i>Wind Frequency Matrices from Table</i> - Tool to compute <b>wind statistics</b>, <b>transport-weighted protection lengths</b> and <b>zone-specific azimuth/altitude parameters</b> following the WERA approach by Funk &amp; V&ouml;lker (2024). The output is a <b>WERA-style table</b> that can be used directly as input for <i>Tool 2: Wind Shade Calculator</i>.
            </p>

            <h2>Standards & References</h2>
            <dt><ul>
            <li><b><a href="https://www.sciencedirect.com/science/article/pii/S2215016124004576">Funk &amp; V&ouml;lker (2024)</a></b>, “A GIS-toolbox for a landscape structure based Wind Erosion Risk Assessment (WERA)” — describes the methodological context of using DWD wind statistics for erosion risk modeling.</li>
            </ul></dt>

            <h2>Inputs</h2>
            <dt><ul>
            <li><b>Custom aggregated wind matrix (CSV)</b>: semicolon-separated table (wind matrix) with structure:
                <dd><ul style="list-style-type:square;">
                <li>First column: <code>vclass</code> (integer wind speed class index; 1 m/s bins, optionally including 0 = calm).</li>
                <li>Remaining columns: wind directions in degrees (e.g. 45, 90, 135, …), values are counts or frequencies.</li>
                </ul></dd>
            <dt><ul>
            </li>
            <li><b>Threshold wind speed u<sub>t</sub> (m/s)</b>: critical wind speed for the onset of wind erosion. Only classes with speed &gt; u<sub>t</sub> contribute to transport and to the effective protection length.</li>
            <li><b>Porosity of shelterbelt (0–1)</b>: porosity <i>p</i> of the windbreak / landscape element, used in the WEPS-based wind reduction function <i>f<sub>u</sub>(x)</i>. Controls the strength and reach of the shelter effect.</li>
            <li><b>Drop directions with zero transport?</b>:if enabled, directions for which no erosive wind events occur (total transport = 0) are omitted from the output table. If disabled, such directions are kept with all zone altitudes set to 0°.</li>
            <li><b>Output table (CSV)</b>: target CSV file for the generated parameter table.</li>
            </ul></dt>

            <h2>Outputs</h2>
            <dt><ul>
            <li><b>WERA-style parameter table (CSV)</b>: This table is designed to be used directly as input for <b>QWERA Toolbox &rarr; Tool 2: Wind Shade Calculator</b>. Each row represents one protection zone for one wind direction, with fields:
                <dd><ul style="list-style-type:square;">
                <li><code>Record</code> — running ID.</li>
                <li><code>Bez</code> — zone label (e.g. <code>r45a</code> … <code>r45f</code>).</li>
                <li><code>Azimut</code> — azimuth of the virtual light source (degrees).</li>
                <li><code>Altitude</code> — altitude angle of the virtual 'light' source (degrees).</li>
                <li><code>Constant</code> — protection zone index (1–5 for leeward zones, 5 for opposite/upwind zone). Will be imprinted into the raster cells.</li>
                </ul></dd>
            </li>
            </ul></dt>

            <h2>Notes</h2>
            <dt><ul>
            <li>The tool assumes <b>1 m/s, equally spaced wind speed classes</b>. Missing integer bins between the minimum and maximum vclass are treated as empty (0 counts). If the vclass values are not equidistant, execution stops with an error so the binning can be checked.</li>
            <li>An overflow class with <code>vclass = inf</code> (open-ended upper bin) is ignored for the calculation.</li>
            <li>Threshold values u<sub>t</sub> around 5–7 m/s are physically meaningful for wind erosion; very low thresholds (e.g. 0 m/s) are not recommended for erosion assessment and may lead to degenerate results.</li>
            <li>This tool is intended to be used after the QWERA DWD downloader &amp; wind matrix tools and before the Windshade Calculator (Tool 2) within the QWERA workflow.</li>
            <li>ChatGPT was used to create this plugin.</li>
            <li>Tested with QGIS 3.44.x (Python 3.12, Windows).</li>
            </ul></dt>
        """
 


    # ------------- Parameter definition ---------------------------------

    def initAlgorithm(self, config=None):
        # Input CSV (semicolon separated)
        self.addParameter(
            QgsProcessingParameterFile(
                self.PARAM_INPUT_CSV,
                self.tr("Custom aggregated wind matrix (CSV)"),
                extension="csv",
                behavior=QgsProcessingParameterFile.File,
            )
        )

        # Threshold wind speed u_t
        self.addParameter(
            QgsProcessingParameterNumber(
                self.PARAM_THRESHOLD,
                self.tr("Threshold wind speed u_t (m/s)"),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=6.0,
                minValue=0.0,
            )
        )

        # Porosity p (0–1)
        self.addParameter(
            QgsProcessingParameterNumber(
                self.PARAM_POROSITY,
                self.tr("Porosity of shelterbelt (0–1)"),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=0.4,
                minValue=0.0,
                maxValue=1.0,
            )
        )

        # Drop empty directions?
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.PARAM_DROP_EMPTY,
                self.tr("Drop directions with zero transport?"),
                defaultValue=True,
            )
        )

        # Output CSV (like WERA table)
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.PARAM_OUTPUT,
                self.tr("Output table (CSV)"),
                "CSV files (*.csv)",
            )
        )

    # ------------- Helper functions -------------------------------------

    @staticmethod
    def _compute_fu_params(p):
        """
        fu(x) parameters according to Funk & Völker / WEPS (as in Excel):

        m = 0.008 - 0.17*p + 0.17*p^1.05
        n = 1.35 * exp(-0.5 * p^0.2)
        s = 10 * (1 - 0.5*p)
        d = 3 - p

        fu(x) = 1 - exp(-m * x^2) + n * exp(-0.003 * (x + s)^d)
        """
        m = 0.008 - 0.17 * p + 0.17 * (p ** 1.05)
        n = 1.35 * math.exp(-0.5 * (p ** 0.2))
        s = 10.0 * (1.0 - 0.5 * p)
        d_exp = 3.0 - p
        return m, n, s, d_exp

    @staticmethod
    def _fu_weps(x, m, n, s, d_exp):
        return 1.0 - math.exp(-m * (x ** 2)) + n * math.exp(-0.003 * ((x + s) ** d_exp))

    @staticmethod
    def _xp_thresholds(p, ut, max_speed_index, x_min=-6, x_max=40):
        """
        Compute xp_threshold(u) for u = 4..max_speed_index m/s
        by scanning x in [x_min, x_max] and taking the largest x
        where u * fu(x) <= ut.
        """
        m, n, s, d_exp = WIND_STATS._compute_fu_params(p)

        def fu(x):
            return WIND_STATS._fu_weps(x, m, n, s, d_exp)

        xp_th = {}
        u_start = max(4, 0)
        for u in range(u_start, max_speed_index + 1):
            valid_x = []
            for x in range(int(x_min), int(x_max) + 1):
                if u * fu(float(x)) <= ut:
                    valid_x.append(x)
            xp_th[u] = max(valid_x) if valid_x else 0
        return xp_th

    @staticmethod
    def _xp_mid_bins(xp_th, max_speed_index):
        """
        Midpoints for consecutive integer speed classes:

        xp_mid(u) = (xp_th(u-1) + xp_th(u)) / 2  for u = 5..max_speed_index
        (only meaningful for u >= 5, because we need u-1 >= 4).
        """
        xp_mid = {}
        for u in range(5, max_speed_index + 1):
            lower = u - 1
            upper = u
            x_low = xp_th.get(lower, 0.0)
            x_up = xp_th.get(upper, 0.0)
            xp_mid[u] = 0.5 * (float(x_low) + float(x_up))
        return xp_mid

    # ------------- Core processing --------------------------------------

    def processAlgorithm(self, parameters, context, feedback):
        input_csv = self.parameterAsFile(parameters, self.PARAM_INPUT_CSV, context)
        ut = self.parameterAsDouble(parameters, self.PARAM_THRESHOLD, context)
        porosity = self.parameterAsDouble(parameters, self.PARAM_POROSITY, context)
        drop_empty = self.parameterAsBool(parameters, self.PARAM_DROP_EMPTY, context)
        output_csv = self.parameterAsFileOutput(parameters, self.PARAM_OUTPUT, context)

        if not os.path.isfile(input_csv):
            raise QgsProcessingException(self.tr("Input CSV not found: {}").format(input_csv))

        if porosity < 0.0 or porosity > 1.0:
            raise QgsProcessingException(self.tr("Porosity must be between 0 and 1."))

        # --- 1) Read CSV and detect directions & vclass indices ---------

        feedback.pushInfo(self.tr("Reading custom aggregation CSV…"))

        # with open(input_csv, newline="", encoding="utf-8-sig") as f:
        #     reader = csv.reader(f, delimiter=";")
        #     rows = list(reader)

        with open(input_csv, newline="", encoding="utf-8-sig") as f:
            # Read a sample to sniff the delimiter
            sample = ""
            for _ in range(10):
                line = f.readline()
                if not line:
                    break
                sample += line

            # Default delimiter
            delimiter = ";"

            if sample.strip():
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=";,\\t")
                    delimiter = dialect.delimiter
                except Exception:
                    # Fallback: keep default ';'
                    pass

            # Reset file to beginning
            f.seek(0)
            reader = csv.reader(f, delimiter=delimiter)
            rows = list(reader)

        if not rows:
            raise QgsProcessingException(self.tr("Input CSV is empty."))

        header = rows[0]
        if len(header) < 2:
            raise QgsProcessingException(
                self.tr("Input CSV must have at least 'vclass' and one direction column.")
            )

        # Direction columns = any header after the first that can be parsed as float
        dir_cols = []
        for idx, name in enumerate(header[1:], start=1):
            name_stripped = (name or "").strip()
            try:
                az = float(name_stripped)
                dir_cols.append((idx, az))
            except ValueError:
                continue

        if not dir_cols:
            raise QgsProcessingException(self.tr("No direction columns found in header."))

        # Collect vclass values (skip inf / NaN)
        speed_indices_set = set()
        for row in rows[1:]:
            if not row:
                continue
            vclass_str = (row[0] or "").strip()
            try:
                v_val = float(vclass_str)
            except ValueError:
                continue

            # Skip infinite or NaN vclass entries (e.g. "inf" row)
            if math.isinf(v_val) or math.isnan(v_val):
                continue

            speed_idx = int(round(v_val))
            speed_indices_set.add(speed_idx)


        if not speed_indices_set:
            raise QgsProcessingException(self.tr("No numeric vclass values found."))

        sorted_speeds = sorted(speed_indices_set)
        min_speed_index = sorted_speeds[0]
        max_speed_index = sorted_speeds[-1]

        # Check if speeds are ~1 m/s apart; if not, raise error
        diffs = [sorted_speeds[i + 1] - sorted_speeds[i]
                 for i in range(len(sorted_speeds) - 1)]
        # allow 1 and gaps that are integer multiples of 1 (we fill missing with zeros)
        non_integer_step = any(abs(d - round(d)) > 1e-6 for d in diffs)
        if non_integer_step:
            raise QgsProcessingException(
                self.tr(
                    "Detected non-integer spacing between vclass values "
                    "(bins are not 1 m/s apart). Please check your DWD "
                    "aggregation binning."
                )
            )

        # If all diffs are integer but some >1, we assume missing 1 m/s bins with 0 events
        if any(d > 1 for d in diffs):
            feedback.pushInfo(
                self.tr(
                    "Detected gaps in vclass indices (missing bins). "
                    "Assuming 1 m/s bins and filling missing speeds with zero counts."
                )
            )

        if min_speed_index < 0:
            raise QgsProcessingException(
                self.tr("Negative vclass indices are not supported.")
            )

        # --- 2) Build complete counts_by_dir for 0..max_speed_index -----

        counts_by_dir = {}
        for _, az in dir_cols:
            counts_by_dir[az] = [0.0] * (max_speed_index + 1)

        # Fill existing bins
        for row in rows[1:]:
            if not row:
                continue
            vclass_str = (row[0] or "").strip()
            try:
                v_val = float(vclass_str)
            except ValueError:
                continue

            # Again, skip inf / NaN vclass entries
            if math.isinf(v_val) or math.isnan(v_val):
                continue

            speed_idx = int(round(v_val))
            if speed_idx < 0 or speed_idx > max_speed_index:
                continue

            for col_idx, az in dir_cols:
                if col_idx >= len(row):
                    continue
                val_str = (row[col_idx] or "").strip()
                if not val_str:
                    continue
                try:
                    count = float(val_str)
                except ValueError:
                    count = 0.0
                counts_by_dir[az][speed_idx] += count

        # Missing 1 m/s classes between min_speed_index and max_speed_index remain 0.0 (no events),
        # which is consistent with the WERA logic.

        # --- 3) q(u_mid) for speeds 0..max_speed_index -------------------

        q_by_speed = [0.0] * (max_speed_index + 1)
        for speed in range(max_speed_index + 1):
            if speed <= ut:
                q_by_speed[speed] = 0.0
            else:
                # interpret class speed as midpoint of [speed-1, speed] m/s
                u_mid = float(speed) - 0.5
                q_val = (u_mid - ut) * (u_mid ** 2)
                if q_val < 0.0:
                    q_val = 0.0
                q_by_speed[speed] = q_val

        # --- 4) T(speed, dir) and T_dir for each direction --------------

        feedback.pushInfo(self.tr("Computing transport per speed and direction…"))

        T_by_dir = {}
        T_dir_sum = {}

        for az, counts in counts_by_dir.items():
            T_speeds = [0.0] * (max_speed_index + 1)
            T_sum = 0.0
            for speed in range(max_speed_index + 1):
                # Apply threshold: only counts in classes with speed > ut are used
                c_thr = counts[speed] if speed > ut else 0.0
                if c_thr <= 0.0:
                    continue
                T_val = q_by_speed[speed] * c_thr
                T_speeds[speed] = T_val
                T_sum += T_val
            T_by_dir[az] = T_speeds
            T_dir_sum[az] = T_sum

        if not T_dir_sum:
            raise QgsProcessingException(self.tr("No transport values could be computed."))

        positive_T = [v for v in T_dir_sum.values() if v > 0.0]
        T_max = max(positive_T) if positive_T else 0.0

        if T_max <= 0.0:
            feedback.pushWarning(
                self.tr(
                    "All directional transports are zero. "
                    "Altitudes will be zero; check threshold and input."
                )
            )

        # --- 5) fu(x), xp thresholds and midpoints ----------------------

        feedback.pushInfo(self.tr("Computing fu(x) and xp thresholds…"))

        xp_th = self._xp_thresholds(porosity, ut, max_speed_index, x_min=-6, x_max=40)
        xp_mid = self._xp_mid_bins(xp_th, max_speed_index)

        # --- 6) Effective protection length L_dir and altitudes ---------

        feedback.pushInfo(self.tr("Computing effective protection length and altitudes…"))

        sorted_dirs = sorted(counts_by_dir.keys())

        rows_out = []
        record_id = 1

        for az in sorted_dirs:
            T_speeds = T_by_dir.get(az, [])
            T_dir = T_dir_sum.get(az, 0.0)

            if T_dir <= 0.0:
                # This direction has no transport at all
                if drop_empty:
                    # skip it entirely
                    continue
                else:
                    P_dir = 0.0
                    L_dir = 0.0
            else:
                P_dir = T_dir / T_max if T_max > 0.0 else 0.0

                L_dir_num = 0.0
                for speed in range(max_speed_index + 1):
                    T_val = T_speeds[speed]
                    if T_val <= 0.0:
                        continue
                    x_mid = xp_mid.get(speed, 0.0)
                    if x_mid <= 0.0:
                        continue
                    L_dir_num += x_mid * T_val
                L_dir = L_dir_num / T_dir if T_dir > 0.0 else 0.0

            # altitudes for zones 1..5 and opposite
            altitudes = [0.0] * 6  # 0..5, index 5 == opposite zone

            if L_dir > 0.0 and P_dir > 0.0:
                for zone in range(1, 6):
                    x_k = (L_dir / 5.0) * (6.0 - float(zone)) * P_dir
                    if x_k > 0.0:
                        alpha = math.degrees(math.atan(1.0 / x_k))
                    else:
                        alpha = 0.0
                    altitudes[zone - 1] = alpha
                altitudes[5] = altitudes[4]  # opposite zone uses zone-5 altitude

            # Opposite azimuth for "f" record
            opp_az = az + 180.0
            if opp_az > 360.0:
                opp_az -= 360.0
            if opp_az <= 0.0:
                opp_az = 360.0

            # WERA-style records: a..e for zones 1..5, f for opposite
            base_az_int = int(round(az))
            for zone in range(1, 6):
                bez = "r{}{}".format(base_az_int, chr(ord("a") + (zone - 1)))
                rows_out.append(
                    [
                        record_id,
                        bez,
                        float(az),
                        float(altitudes[zone - 1]),
                        zone,
                    ]
                )
                record_id += 1

            # Opposite "f" record
            bez_f = "r{}f".format(base_az_int)
            rows_out.append(
                [
                    record_id,
                    bez_f,
                    float(opp_az),
                    float(altitudes[4]),
                    5,
                ]
            )
            record_id += 1

        # --- 7) Write output CSV ----------------------------------------

        feedback.pushInfo(self.tr("Writing output parameter CSV…"))

        out_dir = os.path.dirname(output_csv)
        if out_dir and not os.path.isdir(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        with open(output_csv, "w", newline="", encoding="utf-8") as f_out:
            writer = csv.writer(f_out, delimiter=";")
            writer.writerow(["Record", "Bez", "Azimut", "Altitude", "Constant"])
            for row in rows_out:
                writer.writerow(row)

        feedback.pushInfo(self.tr("Done. Parameter table written to: {}").format(output_csv))

        return {self.PARAM_OUTPUT: output_csv}