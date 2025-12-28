# -*- coding: utf-8 -*-
"""
Lightweight helper for accessing DWD Climate Data Center (CDC) station metadata
without depending on the external `wetterdienst` library.

Aktuell implementiert:
- Stations-Metadaten für stündliche / 10-minütige Winddaten (FF) aus
  FF_Stundenwerte_Beschreibung_Stationen.txt

Wichtig:
- Die Datei wird NICHT mehr als Fixed-Width geparst, sondern robust über
  Tokenisierung (Whitespace / Semikolon) und heuristische Feldzuordnung.
"""

from __future__ import annotations


from qgis.core import QgsBlockingNetworkRequest
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.PyQt.QtCore import QUrl
from typing import Any, Dict, List, Optional, Tuple
import os
import csv
from qgis.core import QgsFeatureRequest, QgsVectorLayer
from qgis.core import QgsProcessingException
import datetime as _dt
from urllib.request import urlopen, Request as _Request
import zipfile
import io
import re
from datetime import datetime

#CDC_BASE_URL = "https://opendata.dwd.de/climate_environment/CDC/observations_germany"

BASE_CDC = (
    "https://opendata.dwd.de/climate_environment/CDC/"
    "observations_germany/climate"
)


class DwdCdcError(RuntimeError):
    """Custom exception for DWD CDC helper."""


# ---------------------------------------------------------------------------
# Download & Basics
# ---------------------------------------------------------------------------

def _download_text(url: str, encoding: str = "latin-1", feedback=None) -> str:
    """
    Kleine Textdateien vom DWD laden und decodieren.

    Stationstabellen sind in der Regel Latin-1 kodiert.
    """
    data = _qgis_http_get_bytes(url, feedback=feedback)

    try:
        return data.decode(encoding, errors="replace")
    except Exception:
        return data.decode("utf-8", errors="replace")


def _parse_float(v: str) -> Optional[float]:
    v = (v or "").strip()
    if not v:
        return None
    # DWD benutzt manchmal Komma
    v = v.replace(",", ".")
    try:
        return float(v)
    except Exception:
        return None


def _parse_date_yyyymmdd(v: str) -> Optional[_dt.date]:
    v = (v or "").strip()
    if not v:
        return None
    # bekannte Missing-Codes
    if v in {"-99999999", "-9999"}:
        return None
    if len(v) != 8 or not v.isdigit():
        return None
    y = int(v[0:4])
    m = int(v[4:6])
    d = int(v[6:8])
    try:
        return _dt.date(y, m, d)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Stationstabellen-Parser (robust, nicht mehr fixed-width)
# ---------------------------------------------------------------------------

def _parse_station_description(text: str) -> List[Dict[str, Any]]:
    """
    FF_Stundenwerte_Beschreibung_Stationen.txt robust parsen.

    Historisch war das eine Fixed-Width-Datei. Inzwischen gibt es Varianten,
    in denen die Spaltenbreiten leicht variieren. Außerdem existieren
    CSV-artige Layouts. Daher:

    - Kommentar- & Kopfzeilen werden an ihrem Inhalt erkannt und übersprungen
      (STATIONS_ID, Stations_id, Legende, #, etc.).
    - Zeilen werden entweder:
      * per ';' in CSV-Spalten aufgetrennt, ODER
      * per Whitespace in Tokens aufgesplittet.
    - Wir gehen von logisch 8 Feldern aus:
      station_id, von, bis, höhe, lat, lon, name, bundesland
      (wie in alten DWD-Beispielen und rdwd-Dokumentation).
    """
    records: List[Dict[str, Any]] = []

    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue

        line = raw_line.rstrip("\n")

        # Kommentar-/Header-Erkennung
        stripped = line.lstrip()
        low = stripped.lower()

        if stripped.startswith("#"):
            continue
        if low.startswith("stations_id") or low.startswith("stationsid"):
            # Kopfzeile mit Spaltennamen
            continue
        if low.startswith("stn") and "geo" in low:
            # alternative Kopfzeilen-Styles
            continue
        if "legende" in low:
            # nach der Legende kommt nichts Interessantes mehr
            break
        if low.startswith("----------") or low.startswith("__________"):
            continue

        # Variante 1: CSV / Semikolon
        if ";" in line:
            parts = [p.strip() for p in line.split(";") if p.strip() != ""]
            # wir erwarten mindestens 6 numerische Felder + Name + Bundesland
            if len(parts) < 6:
                continue

            sid = parts[0]
            von = parts[1] if len(parts) > 1 else ""
            bis = parts[2] if len(parts) > 2 else ""
            h_str = parts[3] if len(parts) > 3 else ""
            lat_str = parts[4] if len(parts) > 4 else ""
            lon_str = parts[5] if len(parts) > 5 else ""

            if len(parts) >= 8:
                # alles dazwischen ist Stationsname, letzte Spalte Bundesland
                name = " ".join(parts[6:-1])
                state = parts[-1]
            elif len(parts) == 7:
                name = parts[6]
                state = ""
            else:
                name = ""
                state = ""

        else:
            # Variante 2: Whitespace-getrennt
            tokens = stripped.split()
            # Wir brauchen mindestens 6 numerische Felder
            if len(tokens) < 6:
                continue

            sid = tokens[0]
            von = tokens[1]
            bis = tokens[2]
            h_str = tokens[3]
            lat_str = tokens[4]
            lon_str = tokens[5]

            if len(tokens) >= 8:
                # alles ab Token 6 bis vor letztem = Name, letzter = Bundesland
                name = " ".join(tokens[6:-1])
                state = tokens[-1]
            elif len(tokens) == 7:
                name = tokens[6]
                state = ""
            else:
                name = ""
                state = ""

        rec: Dict[str, Any] = {
            "station_id": sid.strip(),
            "start_date": _parse_date_yyyymmdd(von),
            "end_date": _parse_date_yyyymmdd(bis),
            "height": _parse_float(h_str),
            "latitude": _parse_float(lat_str),
            "longitude": _parse_float(lon_str),
            "name": name.strip(),
            "state": state.strip(),
        }
        records.append(rec)

    return records


def _normalize_resolution(resolution: str) -> str:
    if not resolution:
        raise DwdCdcError("No resolution given.")
    key = str(resolution).lower().strip()
    key = key.replace("_", "").replace("-", "")
    if key in {"minute10", "10minute", "10min", "min10", "zehnmin"}:
        return "10min"
    if key in {"hourly", "stundenwerte", "stunde"}:
        return "hourly"
    if key.startswith("daily") or key.startswith("day"):
        return "daily"
    if key.startswith("monthly") or key.startswith("month"):
        return "monthly"
    raise DwdCdcError(f"Unsupported resolution '{resolution}'.")


# ---------------------------------------------------------------------------
# Öffentliche API
# ---------------------------------------------------------------------------

def get_wind_station_metadata(
    resolution: str,
    wind_mode: str = "wind_speed",
    feedback: Any = None,
) -> List[Dict[str, Any]]:
    """
    Stationen für Wind-Datensätze liefern.

    - Für 10-Minuten- und Stunden-Wind benutzen wir dieselbe
      Stationsbeschreibung FF_Stundenwerte_Beschreibung_Stationen.txt.
    """
    res_norm = _normalize_resolution(resolution)
    wm = (wind_mode or "wind_speed").lower()

    if wm not in {"wind_speed", "wind_gust_max"}:
        raise DwdCdcError(f"Unsupported wind_mode '{wind_mode}'.")

    if res_norm in {"hourly", "10min"}:
        url = (
            BASE_CDC
            + "/hourly/wind/historical/FF_Stundenwerte_Beschreibung_Stationen.txt"
        )
    else:
        raise DwdCdcError(
            "Wind station metadata is currently only implemented for "
            "hourly and 10-minute resolutions."
        )

    if feedback is not None:
        try:
            feedback.pushInfo(f"Downloading DWD station metadata from {url} ...")
        except Exception:
            pass

    text = _download_text(url)
    records = _parse_station_description(text)

    if not records:
        raise DwdCdcError(
            "No station records parsed from station description file. "
            "The file format might have changed."
        )

    if feedback is not None:
        try:
            feedback.pushInfo(
                f"Parsed {len(records)} station records from DWD station description."
            )
        except Exception:
            pass

    return records


def _as_date(value: Any) -> Optional[_dt.date]:
    if value is None:
        return None
    if isinstance(value, _dt.date) and not isinstance(value, _dt.datetime):
        return value
    if isinstance(value, _dt.datetime):
        return value.date()
    return None


def filter_stations(
    records: List[Dict[str, Any]],
    name_search: Optional[str] = None,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    start_date: Optional[_dt.datetime] = None,
    end_date: Optional[_dt.datetime] = None,
) -> List[Dict[str, Any]]:
    """
    Stationen nach Name, BBOX und Zeitabdeckung filtern.

    bbox: (lon_min, lat_min, lon_max, lat_max) in WGS84
    """
    if not records:
        return []

    name_search_norm = name_search.lower().strip() if name_search else None
    start_d = _as_date(start_date)
    end_d = _as_date(end_date)

    result: List[Dict[str, Any]] = []

    for rec in records:
        # Name
        if name_search_norm:
            nm = (rec.get("name") or "").lower()
            if name_search_norm not in nm:
                continue

        # Räumlicher Filter
        if bbox is not None:
            lon = rec.get("longitude")
            lat = rec.get("latitude")
            if lon is None or lat is None:
                continue
            lon_min, lat_min, lon_max, lat_max = bbox
            if not (lon_min <= lon <= lon_max and lat_min <= lat <= lat_max):
                continue

        # Zeitlicher Filter
        if start_d is not None or end_d is not None:
            frm_d = _as_date(rec.get("start_date"))
            to_d = _as_date(rec.get("end_date"))

            if start_d is not None and to_d is not None and to_d < start_d:
                continue
            if end_d is not None and frm_d is not None and frm_d > end_d:
                continue

        result.append(rec)

    return result


# ============================================================
# Gemeinsame Helfer für alle DWD-Tools (ohne pandas/polars)
# ============================================================

# aktuell nicht genutzt: 
# def records_from_df_like(obj):
#     """
#     Konvertiert ein wetterdienst-Ergebnis in list[dict], ohne pandas/polars zu importieren.

#     Unterstützt:
#       - Polars DataFrame: .to_dicts()
#       - pandas DataFrame: .to_dict('records') / .to_dict(orient='records')
#       - Objekte mit .itertuples + .columns
#       - Iterable[dict]
#     """
#     if obj is None:
#         return []

#     # wetterdienst Result-Objekt hat meist .df
#     df_like = getattr(obj, "df", obj)

#     # Polars
#     to_dicts = getattr(df_like, "to_dicts", None)
#     if callable(to_dicts):
#         try:
#             recs = to_dicts()
#             if isinstance(recs, list) and (not recs or isinstance(recs[0], dict)):
#                 return recs
#         except Exception:
#             pass

#     # pandas
#     to_dict = getattr(df_like, "to_dict", None)
#     if callable(to_dict):
#         try:
#             try:
#                 recs = to_dict(orient="records")
#             except TypeError:
#                 recs = to_dict("records")
#             if isinstance(recs, list) and (not recs or isinstance(recs[0], dict)):
#                 return recs
#         except Exception:
#             pass

#     # generische Table-API
#     itertuples = getattr(df_like, "itertuples", None)
#     columns = getattr(df_like, "columns", None)
#     if callable(itertuples) and columns is not None:
#         try:
#             keys = list(columns)
#             out = []
#             for row in itertuples(index=False, name=None):
#                 out.append({k: v for k, v in zip(keys, row)})
#             if out:
#                 return out
#         except Exception:
#             pass

#     # Iterable[dict]
#     try:
#         lst = list(df_like)
#         if lst and isinstance(lst[0], dict):
#             return lst
#     except Exception:
#         pass

#     return []


def station_ids_from_layer(vl: "QgsVectorLayer", id_field: str, only_selected: bool, feedback):
    """
    Liest Stations-IDs aus einem Vektorlayer (z.B. vom Stationsfinder),
    entfernt Duplikate und füllt numerische IDs auf 5 Stellen mit führenden Nullen.
    """
    ids = []
    if not vl or not id_field:
        return ids

    feats = vl.getSelectedFeatures() if (only_selected and vl.selectedFeatureCount() > 0) else vl.getFeatures(QgsFeatureRequest())
    seen = set()
    for f in feats:
        try:
            v = f[id_field]
            if v is None:
                continue
            s = str(v).strip()
            if not s:
                continue
            s = s.zfill(5) if s.isdigit() else s
            if s not in seen:
                seen.add(s)
                ids.append(s)
        except Exception as e:
            if feedback:
                feedback.reportError(f"Unable to read ID from feature: {e}")
    return ids


def percentile_inc(values, p: float):
    """
    Inklusiver Perzentil-Schätzer (lineare Interpolation), p in [0,1].
    Wird für ff_p90/ff_p95 genutzt.
    """
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


def write_csv(path: str, a, b, delim: str = ";"):
    """
    Robuster CSV-Writer für QWERA:

    Erlaubt beide Aufrufvarianten:
      - write_csv(path, header, rows, ";")
      - write_csv(path, rows, header, ";")

    und versucht anhand der Struktur zu erkennen, was was ist.

    header: Liste von Spaltennamen (Strings)
    rows:   Liste von Zeilen (Liste/Tuple/Dict)
    """
    # --- Heuristik, was wie aussieht ------------------------------------
    def looks_like_header(x):
        # Liste/Tuple von „einfachen“ Werten, KEINE verschachtelten Listen/Dicts
        if not isinstance(x, (list, tuple)):
            return False
        if not x:
            return False
        return not isinstance(x[0], (list, tuple, dict))

    def looks_like_rows(x):
        # Liste/Tuple von Listen/Tuples/Dicts (also Zeilen)
        if not isinstance(x, (list, tuple)):
            return False
        if not x:
            return False
        return isinstance(x[0], (list, tuple, dict))

    header = None
    rows = None

    if looks_like_header(a) and looks_like_rows(b):
        header, rows = a, b
    elif looks_like_rows(a) and looks_like_header(b):
        header, rows = b, a
    else:
        # Fallback: wir behandeln a als header, b als rows
        header, rows = a, b

    if not header:
        return

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=delim)
        w.writerow(header)
        if rows:
            for r in rows:
                # Dict → nach Header-Reihenfolge schreiben
                if isinstance(r, dict):
                    w.writerow([r.get(k, "") for k in header])
                else:
                    w.writerow(r)


# derzeit nicht gebraucht
# def write_dict_csv(path: str, dict_rows, delim=";"):
#     """
#     Schreibt list[dict] als CSV.
#     Header = Vereinigung aller Keys in dict_rows, sortiert für stabile Reihenfolge.
#     """
#     if not dict_rows:
#         return
#     os.makedirs(os.path.dirname(path), exist_ok=True)
#     keys = set()
#     for r in dict_rows:
#         if isinstance(r, dict):
#             keys.update(r.keys())
#     header = sorted(keys)
#     with open(path, "w", newline="", encoding="utf-8") as f:
#         w = csv.writer(f, delimiter=delim)
#         w.writerow(header)
#         for r in dict_rows:
#             row = [r.get(k, "") for k in header]
#             w.writerow(row)


#### DWD Download Helper


def _cdc_http_get_text(url: str, encoding: str = "utf-8", feedback=None) -> str:
    data = _qgis_http_get_bytes(url, feedback=feedback)
    return data.decode(encoding, errors="replace")


def _cdc_http_get_bytes(url: str, feedback = None) -> bytes:
    return _qgis_http_get_bytes(url, feedback=feedback)


def _cdc_list_station_zipfiles(base_url: str, prefix: str, station_id: str, feedback=None) -> list[str]:
    """
    Listet alle ZIP-Dateien für eine Station in einem CDC-Verzeichnis auf.
    base_url: z.B. .../hourly/wind/historical
    prefix:   'stundenwerte_FF_' oder '10minutenwerte_extrema_wind_'
    station_id: 5-stellige ID als String.
    """
    index_url = base_url.rstrip("/") + "/"
    try:
        html = _cdc_http_get_text(index_url, encoding="utf-8")
    except Exception as e:
        if feedback:
            feedback.reportError(f"CDC listing failed: {index_url} ({e})")
        return []

    pattern = re.compile(r'href="(%s%s_[^"]+\.zip)"' % (re.escape(prefix), re.escape(station_id)))
    matches = pattern.findall(html)
    if feedback:
        feedback.pushInfo(f"CDC: Found {len(matches)} zip(s) for station {station_id} in {base_url}.")
    return [index_url + m for m in matches]


def _cdc_parse_datetime(s: str) -> datetime | None:
    s = s.strip()
    if not s:
        return None
    try:
        # typische DWD-MESS_DATUM formate
        if len(s) == 8:
            # YYYYMMDD (falls mal tägliche Daten)
            return datetime.strptime(s, "%Y%m%d")
        if len(s) == 10:
            # YYYYMMDDHH (Stundenwerte)
            return datetime.strptime(s, "%Y%m%d%H")
        if len(s) == 12:
            # YYYYMMDDHHMM (10-Minuten-Werte)
            return datetime.strptime(s, "%Y%m%d%H%M")
        # Fallback: versuch ISO
        try:
            return datetime.fromisoformat(s)
        except Exception:
            return None
    except Exception:
        return None


def _cdc_parse_wind_lines(lines: list[str],
                          station_id: str,
                          wind_mode: str,
                          start_dt: datetime | None,
                          end_dt: datetime | None) -> list[dict]:

    header = None
    idx_sid = idx_date = idx_speed = idx_dir = idx_qn = None
    out: list[dict] = []

    def _find_col_any(cols, candidates):
        """
        Sucht die erste Spalte, deren Name (bereinigt) einem der Kandidaten entspricht
        oder damit beginnt.

        candidates: Liste von möglichen Spaltennamen, z.B. ["F", "FF"].
        """
        norm = []
        for c in cols:
            norm.append(c.strip().upper().replace(" ", ""))

        for cand in candidates:
            cu = cand.upper().replace(" ", "")
            # 1. exakte Treffer
            for i, cc in enumerate(norm):
                if cc == cu:
                    return i
            # 2. Spaltennamen, die damit beginnen (z.B. QN_3 vs QN)
            for i, cc in enumerate(norm):
                if cc.startswith(cu):
                    return i
        return None

    def conv_num(txt: str):
        t = txt.strip()
        if not t or t in {"-999", "-999.0", "-9999"}:
            return None
        try:
            return float(t)
        except Exception:
            return None

    for line in lines:
        if not line:
            continue
        if line.startswith("#"):
            continue

        # --- Kopfzeile einlesen und Spaltenindizes bestimmen -------------
        if header is None:
            header = [c.strip() for c in line.split(";")]

            idx_sid = _find_col_any(header, ["STATIONS_ID", "STATION_ID", "STN_ID", "STN"])
            if idx_sid is None:
                idx_sid = 0  # Fallback

            idx_date = _find_col_any(header, ["MESS_DATUM", "MESS_DATUM_BEGINN", "DATE"])
            if idx_date is None:
                idx_date = 1  # Fallback

            if wind_mode == "wind_speed":
                # Stundenmittel: F (Geschwindigkeit), D (Richtung)
                idx_speed = _find_col_any(header, ["F", "FF"])
                idx_dir   = _find_col_any(header, ["D", "DD"])
            else:
                # 10-Minuten-Extremwind: FX_10 / DX_10
                idx_speed = _find_col_any(header, ["FX_10", "FX"])
                idx_dir   = _find_col_any(header, ["DX_10", "DX"])

            # Qualitätskennzahl – meist QN_3 o.ä.
            idx_qn = _find_col_any(header, ["QN", "QN_3", "QN_FX", "QN_F"])

            continue

        # --- Datensätze --------------------------------------------------
        parts = line.split(";")
        if header is None:
            continue

        needed = [idx_sid, idx_date, idx_speed, idx_dir]
        needed = [i for i in needed if i is not None]
        if any(i >= len(parts) for i in needed):
            continue

        sid = parts[idx_sid].strip() if idx_sid is not None else station_id
        if not sid:
            sid = station_id

        dt = _cdc_parse_datetime(parts[idx_date])
        if dt is None:
            continue
        if start_dt and dt < start_dt:
            continue
        if end_dt and dt > end_dt:
            continue

        ff = conv_num(parts[idx_speed]) if idx_speed is not None else None
        dd = conv_num(parts[idx_dir])   if idx_dir is not None   else None

        qn_val = None
        if idx_qn is not None and idx_qn < len(parts):
            qtxt = parts[idx_qn].strip()
            if qtxt and qtxt not in {"-999", "-9999"}:
                try:
                    qn_val = int(qtxt)
                except Exception:
                    qn_val = None

        if ff is None and dd is None:
            continue

        out.append({
            "station_id": sid,
            "date": dt,
            "ff": ff,
            "dd": dd,
            "qn_ff": qn_val,
            "qn_dd": qn_val,
        })

    return out



def get_wind_timeseries_from_cdc(
    station_ids,
    start: datetime | None,
    end: datetime | None,
    resolution: str,
    wind_mode: str,
    feedback=None,
    ) -> list[dict]:
    """
    Holt Wind-Zeitreihen direkt aus CDC (ohne wetterdienst).

    Rückgabe: Liste von Dicts:
      {station_id, date (datetime), ff, dd, qn_ff, qn_dd}

    resolution:
      - für wind_speed sinnvoll: 'hourly'
      - für wind_gust_max:      'minute_10' (extreme_wind / 10 Minuten)
    wind_mode:
      - 'wind_speed'
      - 'wind_gust_max'
    """

    if not station_ids:
        return []

    # Datumsnormalisierung
    if start and not isinstance(start, datetime):
        start = datetime(start.year, start.month, start.day)
    if end and not isinstance(end, datetime):
        end = datetime(end.year, end.month, end.day)

    if start and end and end <= start:
        raise ValueError("get_wind_timeseries_from_cdc: end must be after start.")

    # effektive Auflösung / Pfade bestimmen
    wind_mode = str(wind_mode or "").strip()
    res_key = str(resolution or "").strip()

    if wind_mode not in {"wind_speed", "wind_gust_max"}:
        raise ValueError(f"Unsupported wind_mode='{wind_mode}'. Use 'wind_speed' or 'wind_gust_max'.")

    if wind_mode == "wind_speed":
        # wir benutzen die Stundenwerte FF/DD
        if res_key != "hourly":
            if feedback:
                feedback.pushInfo("CDC: wind_speed → forcing resolution 'hourly' (FF/DD).")
        hist_base = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly/wind/historical"
        recent_base = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly/wind/recent"
        now_base = None  # gibt es hier i.d.R. nicht
        prefix = "stundenwerte_FF_"
    else:
        # wind_gust_max → 10-Minuten-Extremwind
        if res_key != "minute_10":
            if feedback:
                feedback.pushInfo("CDC: wind_gust_max → forcing resolution 'minute_10' (extreme_wind).")
        hist_base = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/10_minutes/extreme_wind/historical"
        recent_base = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/10_minutes/extreme_wind/recent"
        now_base = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/10_minutes/extreme_wind/now"
        prefix = "10minutenwerte_extrema_wind_"

    all_rows: list[dict] = []

    for sid in station_ids:
        sid_str = str(sid).strip()
        if not sid_str:
            continue
        if sid_str.isdigit():
            sid_str = sid_str.zfill(5)

        if feedback:
            feedback.pushInfo(f"CDC: Fetch data for station {sid_str} …")

        urls: list[str] = []
        for base in (hist_base, recent_base, now_base):
            if not base:
                continue
            urls.extend(_cdc_list_station_zipfiles(base, prefix, sid_str, feedback))

        if not urls:
            if feedback:
                feedback.reportError(f"CDC: No data files found for station {sid_str}.")
            continue

        for url in urls:
            try:
                zbytes = _cdc_http_get_bytes(url)
            except Exception as e:
                if feedback:
                    feedback.reportError(f"CDC: Download failed {url}: {e}")
                continue

            try:
                with zipfile.ZipFile(io.BytesIO(zbytes)) as zf:
                    txt_name = _select_cdc_data_txt_from_zip(zf, wind_mode=wind_mode, station_id=sid_str)
                    if not txt_name:
                        if feedback:
                            feedback.reportError(f"CDC: No suitable data .txt file inside {url}")
                        continue
                    try:
                        content = zf.read(txt_name).decode("latin-1", errors="replace")
                    except Exception as e:
                        if feedback:
                            feedback.reportError(f"CDC: Could not read {txt_name} in {url}: {e}")
                        continue
            except Exception as e:
                if feedback:
                    feedback.reportError(f"CDC: ZIP read failed {url}: {e}")
                continue

            lines = content.splitlines()
            recs = _cdc_parse_wind_lines(lines, sid_str, wind_mode, start, end)
            if feedback:
                feedback.pushInfo(f"CDC: Parsed {len(recs)} rows from {url}")
            all_rows.extend(recs)


    # Überschneidungen historisch/recent/now zusammenführen:
    dedup: dict[tuple, dict] = {}
    for r in all_rows:
        key = (r["station_id"], r["date"])
        if key in dedup:
            old = dedup[key]
            # bevorzugt nicht-None Werte
            for k in ("ff", "dd", "qn_ff", "qn_dd"):
                if old.get(k) is None and r.get(k) is not None:
                    old[k] = r[k]
        else:
            dedup[key] = dict(r)

    ts = list(dedup.values())
    # Filter: nur sinnvolle Paare
    cleaned = []
    for r in ts:
        ff = r.get("ff")
        dd = r.get("dd")
        if ff is None or dd is None:
            continue
        if ff < 0:
            continue
        # Richung normalisieren
        r["dd"] = float(dd) % 360.0
        r["ff"] = float(ff)
        cleaned.append(r)

    cleaned.sort(key=lambda x: (x["station_id"], x["date"]))
    if feedback:
        feedback.pushInfo(f"CDC: Final timeseries length: {len(cleaned)} rows.")
    return cleaned



def _select_cdc_data_txt_from_zip(zf: zipfile.ZipFile,
                                  wind_mode: str,
                                  station_id: str | None = None) -> str | None:
    """
    Wählt aus einem CDC-ZIP die *eigentliche* Produktdatei aus.

    - ignoriert Metadaten-*.txt
    - nutzt Namensmuster wie 'produkt_ff_stunde_' oder 'produkt_zehn_min_fx_'
    - station_id wird aktuell nicht hart verwendet, könnte aber später
      zur Verfeinerung genutzt werden.
    """
    names = zf.namelist()
    txt_names = [n for n in names if n.lower().endswith(".txt")]
    if not txt_names:
        return None

    low_map = {n: n.lower() for n in txt_names}

    wind_mode = (wind_mode or "").lower().strip()

    # Prioritäten-Liste je nach Modus
    if wind_mode == "wind_speed":
        patterns = [
            "produkt_ff_stunde",   # typisches Stundenprodukt
            "produkt_ff_",         # fallback
        ]
    else:
        # 10-Minuten-Extremwind
        patterns = [
            "produkt_zehn_min_fx",  # volle Schreibweise
            "produkt_fx_10",        # alternative Namensgebung
            "produkt_fx_",          # generischer Fallback
        ]

    # 1. Versuch: exakte Produkt-Pattern
    for pat in patterns:
        for orig, low in low_map.items():
            if pat in low:
                return orig

    # 2. Versuch: irgendeine 'produkt_*.txt'
    for orig, low in low_map.items():
        if "produkt_" in low:
            return orig

    # 3. ultimativer Fallback: erste .txt im ZIP
    return txt_names[0]

def _qgis_http_get_bytes(url: str, feedback=None) -> bytes:
    """
    HTTP-GET über QgsBlockingNetworkRequest.

    Achtung: reply() liefert ein QgsNetworkReplyContent-Objekt,
    kein QNetworkReply – also Zugriff über .content(), kein deleteLater().
    """
    req = QNetworkRequest(QUrl(url))
    # Weiterleitungen folgen
    req.setAttribute(QNetworkRequest.FollowRedirectsAttribute, True)

    bn = QgsBlockingNetworkRequest()
    err = bn.get(req)

    if err != QgsBlockingNetworkRequest.NoError:
        msg = bn.errorMessage()
        if feedback:
            try:
                feedback.reportError(f"Network error for URL {url}: {msg}")
            except Exception:
                pass
        raise DwdCdcError(f"Error downloading '{url}': {msg}")

    reply_content = bn.reply()  # QgsNetworkReplyContent
    data = bytes(reply_content.content())  # QByteArray -> bytes
    return data
