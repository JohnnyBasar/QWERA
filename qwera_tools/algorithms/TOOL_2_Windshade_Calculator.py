# -*- coding: utf-8 -*-
"""
TOOL 2: Windshade Calculator (Funk & Völker 2024, Modul 2)
- Liest Excel/CSV mit (Bezeichnung, Azimut, Altitude, Constant)
- Erzeugt pro Zeile eine Shadow-Maske (Float32) für das angegebene LE/DEM
- Speichert alle Masken im Zielordner
Getestet mit QGIS 3.44.x (GDAL 3.11.x)
"""

from typing import List, Dict, Any, Optional
import os
import re
import csv
from pathlib import Path
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterFile,
    QgsProcessingParameterString,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingException,
    QgsRasterLayer,
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsUnitTypes,
)
from qgis.core import QgsApplication
from qgis import processing
from osgeo import gdal, ogr
import numpy as np
import math
import tempfile


class TOOLBOX_2_HILLSHADES(QgsProcessingAlgorithm):
    INPUT_DEM = "INPUT_DEM"
    INPUT_TABLE = "INPUT_TABLE"
    SHEET_NAME = "SHEET_NAME"
    COL_NAME = "COL_NAME"
    COL_AZ = "COL_AZ"
    COL_ALT = "COL_ALT"
    COL_CONST = "COL_CONST"
    OUTPUT_DIR = "OUTPUT_DIR"
    LOAD_OUTPUTS = "LOAD_OUTPUTS"
    PREFIX = "PREFIX"
    SUFFIX = "SUFFIX"
    FAT_SHADOW = "FAT_SHADOW"
    FAT_KERNEL = "FAT_KERNEL"
    USE_SAGA = "USE_SAGA"
    
    # Defaults for octant scan & numerics
    _EDGE_BIAS_PX = -0.5
    _MAX_DIST = 0.0  # unlimited within DEM
    _EPS_M = None    # set per DEM (metric epsilon)

    # NEW: max gap length (in cells) along a ray that will be filled by 1D closing
    __RAY_GAP_MAX = 3  # change this (e.g. 1, 2, 3, ...) to tune aggressiveness

    def icon(self):
        icon_path = os.path.join(os.path.dirname(__file__), "..", "icons", "qwera_tool_2.svg")
        return QIcon(icon_path)

    def name(self):
        return "toolbox_2_windshade_calculator"

    def displayName(self):
        return "Tool 2: Wind Shade Calculator"

    def shortHelpString(self):
        return """
            <h2>Description</h2>
            <p>
            This tool generates <b>shadow masks</b> from the Landscape elements raster (<i>Tool 1: Landscape Elements Calculator</i>) and a  parameter table with <b>azimuth</b>, <b>altitude</b>, and a per-run <b>constant</b> (<i>Wind statistics & shadow parameters</i> Tool). 
            Each row yields one GeoTIFF via an <b>octant-based shadow-scan</b>; sunlit cells are 0.0 and shadowed cells take the given constant (Float32). This refers directly to the approach presented by <b>Funk &amp; V&ouml;lker (2024)</b>. For each given wind direction 5 grids for the 5 wind protection zones are generated. (+ 1 upwind zone)
            The number of octants is <b>inferred automatically</b> from the azimuth list when it is equally spaced. Otherwise, a robust default is used.
            If SAGA Tools are installed, SAGA's analytical hillshading function is used. If this is not found, a internal fallback algorithm is used. The results may differ.
            </p>

            <h2>Standards & References</h2>
            <dt><ul>
            <li><b><a href="https://www.sciencedirect.com/science/article/pii/S2215016124004576">Funk &amp; V&ouml;lker (2024)</a></b>, “A GIS-toolbox for a landscape structure based Wind Erosion Risk Assessment (WERA)” — describes the methodological context of using DWD wind statistics for erosion risk modelling.</li>
            </ul></dt>
            
            <h2>Input</h2>
            <dt><ul>
            <li><b>LE raster</b>: landscape elements raster. Must use a <i>metric CRS</i> (e.g., UTM/ETRS89). The Raster defines extent, resolution, and georeferencing.</li>
            <li><b>Parameter table</b> (CSV or Excel): columns for <i>Name</i>, <i>Azimuth</i> (°), <i>Altitude</i> (°), and <i>Constant</i>.</li>
            <li><b>Sheet name</b>: If the provided Parameter table is an Excel File the name of the sheet containing the parameter table. Leave empty if CSV.</li>
            <li><b>Azimut/Altitude/Constant</b>: Field names containing the specified information.</li>
            <li><b>Prefix/Suffix</b>: optional Suffix or Prefix for output data.</li>
            <li><b>Output writing</b>: shadows → <code>constant</code>, sun → <code>0.0</code>; save as Float32 GeoTIFF (compressed). Optional auto-add to QGIS.</li>
            <li><b>Fat shadows</b> (optional): closes small gaps in the shadow mask and adds a 3x3 or 2x2 dilation, giving slightly thicker, more conservative shadow regions. Only affects the fallback scan, not SAGA</li>
            </ul></dt>
            
            <h2>Output</h2>
            <dt><ul>
            <li><b>Shadow Raster</b>: For each row a raster layer is created. </li>
            </ul></dt>
            
            <h2>Notes</h2>
            <dt><ul>
            <li>DEM CRS must be metric. Otherwise, processing is refused.</li>
            <li>Azimuth normalization treats 360° as 0°; duplicated/invalid entries are ignored when inferring spacing.</li>
            <li>Edge bias is applied internally in the scan; maximum distance is unbounded within the DEM extent.</li>
            <li>ChatGPT was used to create this plugin.</li>
            <li>Tested with QGIS 3.44.x (Python 3.12, GDAL 3.11.x, Windows).</li>
            </ul></dt>
        """

    def createInstance(self):
        return TOOLBOX_2_HILLSHADES()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.INPUT_DEM, "LE raster (metric CRS)"))
        self.addParameter(QgsProcessingParameterFile(self.INPUT_TABLE, "Parameter table (.csv/.xlsx/.xls)", extension=""))
        self.addParameter(QgsProcessingParameterString(self.SHEET_NAME, "Sheet name (Excel, optional)", defaultValue="", optional=True))
        self.addParameter(QgsProcessingParameterString(self.COL_NAME,  "Column name: Bezeichnung", defaultValue="Bez"))
        self.addParameter(QgsProcessingParameterString(self.COL_AZ,    "Column name: Azimut",      defaultValue="Azimut"))
        self.addParameter(QgsProcessingParameterString(self.COL_ALT,   "Column name: Altitude",    defaultValue="Altitude"))
        self.addParameter(QgsProcessingParameterString(self.COL_CONST, "Column name: Constant",    defaultValue="Constant"))
        self.addParameter(QgsProcessingParameterString(self.PREFIX,    "Prefix", defaultValue="", optional=True))
        self.addParameter(QgsProcessingParameterString(self.SUFFIX,    "Suffix", defaultValue="", optional=True))


        # Prefer SAGA Analytical Hillshading (if available)
        self.addParameter(QgsProcessingParameterBoolean(
            self.USE_SAGA,
            "Prefer SAGA analytical hillshading (METHOD=3 'Shadows Only') with fallback",
            defaultValue=True
        ))

        # Fat shadows: on/off
        self.addParameter(QgsProcessingParameterBoolean(
            self.FAT_SHADOW,
            "Fat shadows on (only affects the fallback scan, not SAGA)",
            defaultValue=False
        ))

        # Kernel size for fat shadows
        self.addParameter(QgsProcessingParameterEnum(
            self.FAT_KERNEL,
            "Size of the fat shadow (not SAGA)",
            options=["3x3", "2x2"],
            defaultValue=0
        ))

        # Prefer SAGA Analytical Hillshading (if available)
        self.addParameter(QgsProcessingParameterBoolean(
            self.USE_SAGA,
            "Prefer SAGA analytical hillshading (METHOD=3 'Shadows Only') with fallback",
            defaultValue=True
        ))

        self.addParameter(QgsProcessingParameterFolderDestination(self.OUTPUT_DIR, "Output folder"))
        self.addParameter(QgsProcessingParameterBoolean(self.LOAD_OUTPUTS, "Load outputs into QGIS", defaultValue=False))


    def _to_float(self, v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip().replace(",", ".")
        try:
            return float(s)
        except Exception:
            return None

    def _slug(self, name):
        out = []
        for ch in (name or "").strip():
            out.append(ch if (ch.isalnum() or ch in ".-_") else "_")
        s = "".join(out).strip(" .")
        return s if s else "shadow"

    def _read_csv(self, path, col_name, col_az, col_alt, col_const):
        rows = []

        # auto-detect delimiter (comma vs semicolon)
        with open(path, "r", newline="", encoding="utf-8-sig") as f:
            # peek first non-empty line
            first_line = ""
            while first_line == "":
                first_line = f.readline()
                if not first_line:
                    raise QgsProcessingException("CSV file is empty.")
                first_line = first_line.strip()

            # very simple heuristic: more ; → semicolon, otherwise comma
            delim = ";"
            if first_line.count(",") > first_line.count(";"):
                delim = ","

            # rewind to beginning for DictReader
            f.seek(0)

            rdr = csv.DictReader(f, delimiter=delim)
            headers = {(h or "").lower(): (h or "") for h in (rdr.fieldnames or [])}

            def pick(col):
                return headers.get((col or "").lower(), col)

            cn, caz, calt, cconst = pick(col_name), pick(col_az), pick(col_alt), pick(col_const)

            for r in rdr:
                rows.append({
                    "name":     r.get(cn, ""),
                    "azimuth":  self._to_float(r.get(caz)),
                    "altitude": self._to_float(r.get(calt)),
                    "constant": self._to_float(r.get(cconst)),
                })

        return rows

    def _read_excel_ogr(self, path, sheet_name, col_name, col_az, col_alt, col_const):
        rows = []
        ds = ogr.Open(path)
        if ds is None:
            raise QgsProcessingException("Excel file could not be opened.")
        lyr = ds.GetLayerByName(sheet_name) if sheet_name else (ds.GetLayer(0) if ds.GetLayerCount() > 0 else None)
        if lyr is None:
            raise QgsProcessingException("No Excel sheet found.")
        fmap = {}
        ld = lyr.GetLayerDefn()
        for i in range(ld.GetFieldCount()):
            fdef = ld.GetFieldDefn(i)
            fmap[(fdef.GetName() or "").lower()] = fdef.GetName()
        def pick(col):
            return fmap.get((col or "").lower(), col)
        cn, caz, calt, cconst = pick(col_name), pick(col_az), pick(col_alt), pick(col_const)
        lyr.ResetReading()
        feat = lyr.GetNextFeature()
        while feat:
            rows.append({
                "name":     feat.GetField(cn)      if feat.GetFieldIndex(cn)      != -1 else "",
                "azimuth":  self._to_float(feat.GetField(caz)    if feat.GetFieldIndex(caz)    != -1 else None),
                "altitude": self._to_float(feat.GetField(calt)   if feat.GetFieldIndex(calt)   != -1 else None),
                "constant": self._to_float(feat.GetField(cconst) if feat.GetFieldIndex(cconst) != -1 else None),
            })
            feat = lyr.GetNextFeature()
        ds.Destroy()
        return rows

    def _read_table(self, table_path, sheet_name, col_name, col_az, col_alt, col_const):
        ext = (os.path.splitext(table_path)[1] or "").lower()
        if ext == ".csv":
            return self._read_csv(table_path, col_name, col_az, col_alt, col_const)
        if ext in (".xlsx", ".xls"):
            return self._read_excel_ogr(table_path, sheet_name, col_name, col_az, col_alt, col_const)
        raise QgsProcessingException("Only .csv, .xlsx, and .xls formats are supported.")

    @staticmethod
    def infer_octants_from_azimuths(az_values, tolerance_deg=0.5, min_parts=4, default_octants=32):
        import numpy as np
        az = np.array([float(a) for a in az_values if a is not None and not np.isnan(a)], dtype=float)
        az = np.mod(az, 360.0)  # [0,360)
        az = np.unique(np.round(az, 6))
        n = len(az)
        if n < min_parts:
            return default_octants
        az_sorted = np.sort(az)
        diffs = np.diff(az_sorted)
        diffs = np.append(diffs, 360.0 - (az_sorted[-1] - az_sorted[0]))
        mean_step = np.mean(diffs)
        if mean_step <= 0:
            return default_octants
        max_dev = np.max(np.abs(diffs - mean_step))
        if max_dev <= tolerance_deg and (350.0 <= np.sum(diffs) <= 370.0):
            return int(round(360.0 / mean_step))
        else:
            return default_octants

    def _prepare_dem(self, dem_layer, feedback: QgsProcessingFeedback):
        src = dem_layer.source()
        ds = gdal.Open(src, gdal.GA_ReadOnly)
        if ds is None:
            raise QgsProcessingException("LE raster could not be opened.")

        band = ds.GetRasterBand(1)
        Z = band.ReadAsArray()
        if Z is None:
            band = None
            ds = None
            raise QgsProcessingException("DEM band could not be read.")

        Z = Z.astype(np.float32, copy=False)

        nodata = band.GetNoDataValue()
        if nodata is None:
            nodata = -9999.0
        nodata = float(nodata)

        mask_nd = ~np.isfinite(Z) | (Z == nodata)
        Z[mask_nd] = np.nan  # allow NaN-based masking

        gt = ds.GetGeoTransform()
        proj = ds.GetProjection()
        ny, nx = Z.shape

        band = None
        ds = None

        feedback.pushInfo(f"DEM loaded once: {nx} x {ny} cells")

        return {
            "Z": Z,
            "mask_nd": mask_nd,
            "nodata": nodata,
            "gt": gt,
            "proj": proj,
            "ny": ny,
            "nx": nx,
        }

    def _write_shadow_mask(self, dem_info, shadow_bool, out_path, const_val=1.0):
        """Writes a Float32 GeoTIFF: shadow -> constant, sun -> 0, DEM no-data -> DEM nodata.

        Also enforces the 'LE pixels are always class 5' rule for const==5.
        """
        Z       = dem_info["Z"]
        mask_nd = dem_info["mask_nd"]
        nodata  = float(dem_info["nodata"])
        gt      = dem_info["gt"]
        proj    = dem_info["proj"]
        ny      = dem_info["ny"]
        nx      = dem_info["nx"]

        shadow = np.array(shadow_bool, dtype=bool, copy=False)
        if shadow.shape != (ny, nx):
            raise QgsProcessingException("Shadow mask dimensions do not match input raster.")

        shadow[mask_nd] = False

        # Heights raster convention: LE > 0
        mask_le = (~mask_nd) & np.isfinite(Z) & (Z > 0.0)

        c = float(const_val) if const_val is not None else 1.0
        out = np.where(shadow, c, 0.0).astype(np.float32)

        # Enforce LE only for the class-5 raster
        if abs(c - 5.0) < 1e-6:
            out[mask_le] = 5.0

        out[mask_nd] = nodata

        drv = gdal.GetDriverByName("GTiff")
        ods = drv.Create(
            str(out_path),
            nx,
            ny,
            1,
            gdal.GDT_Float32,
            options=[
                "TILED=YES",
                "COMPRESS=DEFLATE",
                "PREDICTOR=3",
                "ZLEVEL=6",
                "BIGTIFF=IF_SAFER",
            ],
        )
        ods.SetGeoTransform(gt)
        ods.SetProjection(proj)
        b = ods.GetRasterBand(1)
        b.WriteArray(out)
        b.SetNoDataValue(nodata)
        b.FlushCache()
        ods.FlushCache()
        ods = None

    def _saga_shadow_mask(self, dem_layer, az, alt, context, feedback):
        """Runs SAGA 'Analytical Hillshading' with METHOD=3 ('Shadows Only') and returns a boolean mask."""
        res = processing.run(
            "sagang:analyticalhillshading",
            {
                "ELEVATION": dem_layer,
                "SHADE": QgsProcessing.TEMPORARY_OUTPUT,
                "METHOD": 3,        # Shadows Only
                "POSITION": 0,      # azimuth and height
                "AZIMUTH": float(az),
                "DECLINATION": float(alt),
                "EXAGGERATION": 1.0,
                "UNIT": 0,          # radians (irrelevant for METHOD=3, but required by interface)
                "SHADOW": 1,        # 'fat' shadow tracing (more conservative)
                "NDIRS": 8,         # used for Ambient Occlusion only (METHOD=4)
                "RADIUS": 10.0,     # used for Ambient Occlusion only (METHOD=4)
            },
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )

        shade_path = res.get("SHADE")
        if not shade_path:
            raise QgsProcessingException("SAGA output 'SHADE' not returned.")

        ds = gdal.Open(str(shade_path), gdal.GA_ReadOnly)
        if ds is None:
            raise QgsProcessingException("SAGA shade raster could not be opened.")
        band = ds.GetRasterBand(1)
        arr = band.ReadAsArray()
        ndv = band.GetNoDataValue()
        band = None
        ds = None

        if arr is None:
            raise QgsProcessingException("SAGA shade raster could not be read.")

        arr = arr.astype(np.float32, copy=False)
        nodata_mask = ~np.isfinite(arr)
        if ndv is not None:
            nodata_mask |= (arr == float(ndv))

        # METHOD=3: sunlit cells are NoData, shadowed cells have a value (typically 90° / pi/2).
        return ~nodata_mask

    @staticmethod
    def _close_and_optionally_dilate(mask_bool, extra_dilate=False, kernel_size=3):
        """Applies a 3x3 binary closing, optionally followed by an extra dilation (3x3 or 2x2)."""

        def _binary_dilate(m, k=3):
            ny_, nx_ = m.shape
            padded = np.pad(m, 1, mode="constant", constant_values=False)
            if k == 2:
                a = padded[0:ny_,     0:nx_]
                b = padded[0:ny_,     1:nx_+1]
                c = padded[1:ny_+1,   0:nx_]
                d = padded[1:ny_+1,   1:nx_+1]
                return a | b | c | d
            neigh = [
                padded[0:-2, 0:-2], padded[0:-2, 1:-1], padded[0:-2, 2:],
                padded[1:-1, 0:-2], padded[1:-1, 1:-1], padded[1:-1, 2:],
                padded[2:,   0:-2], padded[2:,   1:-1], padded[2:,   2:],
            ]
            return np.logical_or.reduce(neigh)

        m = np.array(mask_bool, dtype=bool, copy=False)
        d1 = _binary_dilate(m, k=3)
        e1 = ~_binary_dilate(~d1, k=3)
        m = e1

        if extra_dilate:
            m = _binary_dilate(m, k=kernel_size)

        return m

    def _compute_shadow_octant(self, dem_info, az, alt, out_path, octants, maxd, edge_bias_px, feedback, const_val=1.0, fat_shadow=False, fat_kernel=3):
        """
        Shadow via strip-sweep in sun coordinates.
        Walks strips perpendicular to sun direction; in each strip, processes cells from sunward to lee.
        Uses DEM already loaded in dem_info (no GDAL I/O here).
        """
        Z       = dem_info["Z"]
        mask_nd = dem_info["mask_nd"]
        nodata  = dem_info["nodata"]
        gt      = dem_info["gt"]
        proj    = dem_info["proj"]
        ny      = dem_info["ny"]
        nx      = dem_info["nx"]

        cellx = float(abs(gt[1]))
        celly = float(abs(gt[5]))

        if self._EPS_M is None:
            self._EPS_M = 1e-5 * max(cellx, celly)
        eps_m = self._EPS_M

        # solar geometry
        azr = math.radians((450.0 - float(az)) % 360.0)
        tan_alt = math.tan(math.radians(float(alt)))

        # sun direction: FROM sun TO ground
        ux = -math.cos(azr)
        uy = -math.sin(azr)

        # pixel steps in meters
        vx_col_x, vx_col_y = cellx, 0.0
        vx_row_x, vx_row_y = 0.0, -celly

        # along-sun increments
        dL_col = vx_col_x * ux + vx_col_y * uy
        dL_row = vx_row_x * ux + vx_row_y * uy

        # perpendicular direction (rotate sun by +90°)
        upx, upy = -uy, ux
        dS_col = vx_col_x * upx + vx_col_y * upy
        dS_row = vx_row_x * upx + vx_row_y * upy

        # treat tiny dS_* as zero consistently
        dir_eps = 1e-9
        if abs(dS_col) < dir_eps:
            dS_col = 0.0
        if abs(dS_row) < dir_eps:
            dS_row = 0.0

        # strip width
        strip_w = max(
            1e-9,
            min(
                abs(dS_col) if abs(dS_col) > 0.0 else float("inf"),
                abs(dS_row) if abs(dS_row) > 0.0 else float("inf"),
            ),
        )

        # S-range from DEM corners
        corners = [(0, 0), (0, nx - 1), (ny - 1, 0), (ny - 1, nx - 1)]
        S_vals = [i * dS_row + j * dS_col for (i, j) in corners]
        Smin, Smax = min(S_vals), max(S_vals)
        s_idx_min = int(round(Smin / strip_w)) - 1
        s_idx_max = int(round(Smax / strip_w)) + 1

        shadow = np.zeros((ny, nx), dtype=bool)

        total_strips = max(1, s_idx_max - s_idx_min + 1)
        p_every = max(1, total_strips // 50)

        gap_max = int(self.__RAY_GAP_MAX) if self.__RAY_GAP_MAX is not None else 0
        if gap_max < 0:
            gap_max = 0

        for si, s_idx in enumerate(range(s_idx_min, s_idx_max + 1)):
            if feedback and feedback.isCanceled():
                raise QgsProcessingException("Aborted")

            cells_i = []
            S_target = s_idx * strip_w
            half_w = 0.5 * strip_w

            for i in range(ny):
                if abs(dS_col) > dir_eps:
                    j_star = (S_target - i * dS_row) / dS_col
                    j0 = max(0, int(math.floor(j_star - 1)))
                    j1 = min(nx - 1, int(math.ceil(j_star + 1)))
                    j_range = range(j0, j1 + 1)
                else:
                    S_row0 = i * dS_row
                    if abs(S_row0 - S_target) > half_w:
                        continue
                    j_range = range(0, nx)

                for j in j_range:
                    S_ij = i * dS_row + j * dS_col
                    if abs(S_ij - S_target) <= half_w:
                        if not mask_nd[i, j]:
                            L_ij = i * dL_row + j * dL_col
                            cells_i.append((L_ij, i, j))

            if not cells_i:
                if feedback and (si % p_every == 0):
                    feedback.setProgress(100.0 * si / float(total_strips))
                continue

            # sort sunward -> lee
            cells_i.sort(key=lambda t: t[0])

            L0 = cells_i[0][0]
            horizon = -1e38

            # horizon-based classification
            for (Lk, i, j) in cells_i:
                d = (Lk - L0)
                z = float(Z[i, j])
                T = z + tan_alt * d
                if horizon > T - eps_m:
                    shadow[i, j] = True
                if T > horizon:
                    horizon = T
                if maxd > 0 and d > maxd:
                    break

            # --- 1D closing along this strip: fill short lit gaps between shadow segments ---
            if cells_i and gap_max > 0:
                vals = [shadow[i, j] for (_, i, j) in cells_i]
                n_vals = len(vals)
                if n_vals >= 3:
                    k = 0
                    while k < n_vals:
                        if vals[k]:
                            k += 1
                            continue
                        # start of a run of False
                        start = k
                        while k < n_vals and not vals[k]:
                            k += 1
                        end = k - 1
                        gap_len = end - start + 1
                        left_true = (start - 1 >= 0 and vals[start - 1])
                        right_true = (end + 1 < n_vals and vals[end + 1])
                        if left_true and right_true and gap_len <= gap_max:
                            for t in range(start, end + 1):
                                vals[t] = True
                    # write back
                    for val, (_, i, j) in zip(vals, cells_i):
                        shadow[i, j] = val

            if feedback and (si % p_every == 0):
                feedback.setProgress(100.0 * si / float(total_strips))

        shadow[mask_nd] = False

        # 3x3 morphological closing (2D) to fill remaining small holes
        # --- helper: binary dilation with 3x3 or 2x2 kernel ----------------
        def _binary_dilate(mask_bool, kernel_size=3):
            ny_, nx_ = mask_bool.shape
            padded = np.pad(mask_bool, 1, mode="constant", constant_values=False)

            if kernel_size == 2:
                # 2x2 kernel: OR over four 2x2 windows around each cell
                a = padded[0:ny_,     0:nx_]
                b = padded[0:ny_,     1:nx_+1]
                c = padded[1:ny_+1,   0:nx_]
                d = padded[1:ny_+1,   1:nx_+1]
                return a | b | c | d
            else:
                # default: full 3x3 neighbourhood
                neigh = [
                    padded[0:-2, 0:-2], padded[0:-2, 1:-1], padded[0:-2, 2:],
                    padded[1:-1, 0:-2], padded[1:-1, 1:-1], padded[1:-1, 2:],
                    padded[2:,   0:-2], padded[2:,   1:-1], padded[2:,   2:],
                ]
                return np.logical_or.reduce(neigh)

        d1 = _binary_dilate(shadow, kernel_size=3)
        e1 = ~_binary_dilate(~d1, kernel_size=3)
        shadow[:, :] = e1

        # optional extra dilation for 'fat' shadows
        if fat_shadow:
            shadow[:, :] = _binary_dilate(shadow, kernel_size=fat_kernel)

        # Write output using DEM no-data mask and class-5 enforcement.
        self._write_shadow_mask(dem_info, shadow, out_path, const_val=const_val)

    def processAlgorithm(self, parameters, context, feedback):
        self._EPS_M = None

        dem_layer = self.parameterAsRasterLayer(parameters, self.INPUT_DEM, context)
        if dem_layer is None:
            raise QgsProcessingException("LE raster could not be loaded.")
        if dem_layer.crs().mapUnits() != QgsUnitTypes.DistanceMeters:
            raise QgsProcessingException("CRS must be metric (UTM/ETRS89).")

        table_path = self.parameterAsFile(parameters, self.INPUT_TABLE, context)
        if not table_path or not os.path.exists(table_path):
            raise QgsProcessingException("No valid table specified.")

        sheet_name = self.parameterAsString(parameters, self.SHEET_NAME, context).strip()
        col_name   = self.parameterAsString(parameters, self.COL_NAME,  context).strip() or "Bez"
        col_az     = self.parameterAsString(parameters, self.COL_AZ,    context).strip() or "Azimut"
        col_alt    = self.parameterAsString(parameters, self.COL_ALT,   context).strip() or "Altitude"
        col_const  = self.parameterAsString(parameters, self.COL_CONST, context).strip() or "Constant"

        prefix = self.parameterAsString(parameters, self.PREFIX, context) or ""
        suffix = self.parameterAsString(parameters, self.SUFFIX, context) or ""
        out_dir = self.parameterAsFileOutput(parameters, self.OUTPUT_DIR, context)
        if not out_dir:
            raise QgsProcessingException("Missing output folder.")
        if not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        load_outputs = self.parameterAsBoolean(parameters, self.LOAD_OUTPUTS, context)
        fat_shadow = self.parameterAsBoolean(parameters, self.FAT_SHADOW, context)
        fat_kernel_idx = self.parameterAsEnum(parameters, self.FAT_KERNEL, context)
        fat_kernel = 3 if fat_kernel_idx == 0 else 2
        prefer_saga = self.parameterAsBoolean(parameters, self.USE_SAGA, context)
        
        dem_info = self._prepare_dem(dem_layer, feedback)

        rows = self._read_table(table_path, sheet_name, col_name, col_az, col_alt, col_const)
        if not rows:
            raise QgsProcessingException("Table contains no data.")

        azimuths = [row.get("azimuth") for row in rows if row.get("azimuth") is not None]
        octs = self.infer_octants_from_azimuths(azimuths, tolerance_deg=0.25, min_parts=4, default_octants=32)
        feedback.pushInfo(f"Inferred octants: {octs}")
        self._OCTANTS = octs

        created = []
        total_rows = len(rows)
        feedback.pushInfo("Rows: " + str(total_rows))

        # If SAGA is missing or fails systematically, disable after the first hard failure
        saga_enabled = bool(prefer_saga)

        for idx, row in enumerate(rows, start=1):
            if feedback.isCanceled():
                break

            name = (row.get("name") or "").strip()
            az   = self._to_float(row.get("azimuth"))
            alt  = self._to_float(row.get("altitude"))
            cval = self._to_float(row.get("constant"))
            if not name or az is None or alt is None or cval is None:
                feedback.reportError(f"Row {idx}: incomplete (Name/Az/Alt/Constant) – skipped.")
                continue

            safe = self._slug(name)
            ctag = str(int(cval)) if float(cval).is_integer() else ("%g" % float(cval))
            fn = f"{prefix}{safe}{suffix}_sm_az{int(round(az))}_alt{int(round(alt))}_c{ctag}.tif"
            out_path = os.path.join(out_dir, fn)

            feedback.pushInfo(f"[{idx}/{total_rows}] {name}: AZ={az}, ALT={alt}, CONST={cval} -> {fn}")

            try:
                if saga_enabled:
                    try:
                        shadow_mask = self._saga_shadow_mask(dem_layer, float(az), float(alt), context, feedback)
                        # IMPORTANT:
                        # The plugin's own "Fat shadows" post-processing (closing + dilation)
                        # shall ONLY be applied to the internal fallback shadow-scan.
                        # When SAGA succeeds, we keep the SAGA result as-is.
                        self._write_shadow_mask(dem_info, shadow_mask, out_path, const_val=float(cval))
                    except Exception as saga_err:
                        feedback.reportError(f"SAGA analytical hillshading failed for '{name}' (AZ={az}, ALT={alt}). Falling back to internal shadow scan. Details: {saga_err}")
                        # If the algorithm is not available (or SAGA provider is missing), stop trying for subsequent rows.
                        msg = str(saga_err).lower()
                        if "not found" in msg or "algorithm" in msg and "not" in msg and "found" in msg or "sagang" in msg:
                            saga_enabled = False

                        self._compute_shadow_octant(
                            dem_info,
                            float(az),
                            float(alt),
                            out_path,
                            octants=self._OCTANTS,
                            maxd=self._MAX_DIST,
                            edge_bias_px=self._EDGE_BIAS_PX,
                            feedback=feedback,
                            const_val=float(cval),
                            fat_shadow=fat_shadow,
                            fat_kernel=fat_kernel,
                        )
                else:
                    self._compute_shadow_octant(
                        dem_info,
                        float(az),
                        float(alt),
                        out_path,
                        octants=self._OCTANTS,
                        maxd=self._MAX_DIST,
                        edge_bias_px=self._EDGE_BIAS_PX,
                        feedback=feedback,
                        const_val=float(cval),
                        fat_shadow=fat_shadow,
                        fat_kernel=fat_kernel,
                    )
                created.append(out_path)
            except Exception as e:
                feedback.reportError(f"Error '{name}': {e}")
                continue

            feedback.setProgress(100.0 * idx / float(total_rows))

            if load_outputs and os.path.exists(out_path):
                try:
                    rlayer = QgsRasterLayer(out_path, os.path.splitext(os.path.basename(out_path))[0])
                    if rlayer.isValid():
                        QgsProject.instance().addMapLayer(rlayer)
                except Exception:
                    pass

        if not created:
            raise QgsProcessingException("No shadow masks were created.")

        feedback.pushInfo("Done. Generated rasters: " + str(len(created)))
        return {"OUTPUT_DIR": out_dir, "OUTPUT_FILES": created}


def classFactory(iface=None):
    return TOOLBOX_2_HILLSHADES()
