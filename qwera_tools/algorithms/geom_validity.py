# -*- coding: utf-8 -*-
from qgis.core import QgsApplication, QgsProcessing
import processing

## helper check validity

# simple module-level cache
_ALG_CACHE = {}

def _alg_exists(alg_id: str) -> bool:
    return QgsApplication.processingRegistry().algorithmById(alg_id) is not None

def _pick_alg(cache_key: str, preferred_ids):
    if cache_key in _ALG_CACHE:
        return _ALG_CACHE[cache_key]
    for a in preferred_ids:
        if _alg_exists(a):
            _ALG_CACHE[cache_key] = a
            return a
    raise RuntimeError(f"Processing algorithm not available: {preferred_ids}")

def check_and_fix_validity(vlayer, context, feedback, name):
    check_alg = _pick_alg("checkvalidity", ["qgis:checkvalidity", "native:checkvalidity"])
    fix_alg   = _pick_alg("fixgeometries", ["qgis:fixgeometries", "native:fixgeometries"])
    stats_alg = _pick_alg("basicstats", ["qgis:basicstatisticsforfields", "native:basicstatisticsforfields"])

    # 1) Validate geometries (tolerate INPUT vs INPUT_LAYER)
    base_params = {
        "VALID_OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        "INVALID_OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
        "ERROR_OUTPUT": QgsProcessing.TEMPORARY_OUTPUT,
    }

    try:
        params = dict(base_params)
        params["INPUT_LAYER"] = vlayer
        res = processing.run(
            check_alg, params,
            context=context, feedback=feedback, is_child_algorithm=True
        )
    except Exception:
        params = dict(base_params)
        params["INPUT"] = vlayer
        res = processing.run(
            check_alg, params,
            context=context, feedback=feedback, is_child_algorithm=True
        )

    invalid_lyr = res.get("INVALID_OUTPUT")
    error_pts   = res.get("ERROR_OUTPUT")

    # 2) Count invalid features robustly
    if "INVALID_COUNT" in res and res["INVALID_COUNT"] is not None:
        invalid_count = int(res["INVALID_COUNT"])
    else:
        try:
            invalid_count = invalid_lyr.featureCount() if invalid_lyr else 0
        except Exception:
            invalid_count = 0

    feedback.pushInfo(f"[{name}] invalid features: {invalid_count}")

    # 3) Optional: summarize error types (try common field names)
    if invalid_count and error_pts:
        for fld in ("message", "MESSAGE", "error", "ERROR", "reason", "REASON"):
            try:
                stats = processing.run(
                    stats_alg,
                    {"INPUT_LAYER": error_pts, "FIELD_NAME": fld},
                    context=context, feedback=feedback, is_child_algorithm=True
                )["STATISTICS"]
                feedback.pushInfo(f"[{name}] error summary ({fld}): {stats.get('UNIQUE_VALUES', 'n/a')} types")
                break
            except Exception:
                continue

    # 4) Repair only if necessary
    if invalid_count > 0:
        feedback.pushInfo(f"[{name}] fixing geometries (fixgeometries)…")
        fixed = processing.run(
            fix_alg,
            {"INPUT": vlayer, "OUTPUT": QgsProcessing.TEMPORARY_OUTPUT},
            context=context, feedback=feedback, is_child_algorithm=True
        )["OUTPUT"]
        return fixed, invalid_lyr, error_pts

    # 5) If all valid, return original
    return vlayer, invalid_lyr, error_pts
