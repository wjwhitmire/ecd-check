"""Annular hydraulics screening: API RP 13D (Third Edition, June 1995) power-law annulus model.

All inputs and outputs use oilfield units:
    mud weight ppg, dial readings in degrees (approximately lbf/100 ft^2),
    PV cP, YP lbf/100 ft^2, flow rate gpm, diameters in, lengths ft, pressures psi.

This is a screening tool, not a replacement for a full hydraulics program.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

__all__ = [
    "InputError",
    "VA_CONST",
    "HYDROSTATIC_CONST",
    "EXAMPLE_CASE",
    "dial_from_pv_yp",
    "rheology_params",
    "friction_factor",
    "section_hydraulics",
    "evaluate",
    "ecd_sweep",
    "default_sweep_rates",
    "normalize_case",
    "sweep_dips",
    "density_checks",
    "ECD_MAX_PLAUSIBLE_PPG",
    "ECD_RISE_FLAG_PPG",
    "FRAC_NEAR_PPG",
]

# Screening limits for the warnings in density_checks().
ECD_MAX_PLAUSIBLE_PPG = 25.0  # heavier than any drilling fluid this tool accepts
ECD_RISE_FLAG_PPG = 2.0  # annular friction adding more than this to MW is unusual for a drilling annulus
FRAC_NEAR_PPG = 0.3  # margin to the fracture gradient below which the result is flagged

# Annular velocity constant, ft/min per (gpm / in^2). API RP 13D (1995) writes
# Va = 0.408 Q / (D2^2 - D1^2) in ft/s; 0.408 * 60 = 24.48 ft/min.
VA_CONST = 24.48
# Hydrostatic gradient constant, psi/ft per ppg.
HYDROSTATIC_CONST = 0.052
# Reynolds number constant for ppg, in, ft/s, cP.
RE_CONST = 928.0
# Pressure loss constant for ppg, in, ft/s, giving psi/ft (Fanning, 2 f rho v^2 / Dh).
DP_CONST = 25.81
# Fann dial reading (deg) to shear stress (dyne/cm^2) for a standard R1B1 F1 viscometer.
DIAL_TO_DYNE = 5.11
# Shear rate in s^-1 of the 100 rpm and 300 rpm speeds (1.703 s^-1 per rpm).
SHEAR_100 = 170.2
SHEAR_300 = 511.0

RPMS = (600, 300, 200, 100, 6, 3)
REQUIRED_FANN = (600, 300, 100, 3)


_NUM_RE = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


class InputError(ValueError):
    """Raised for inputs the model cannot evaluate. The message is meant for a person."""


def _num(value: Any, label: str) -> float:
    if isinstance(value, bool) or value is None:
        raise InputError(f"{label} must be a number.")
    if isinstance(value, str) and not _NUM_RE.match(value.strip()):
        raise InputError(f"{label} must be a number, got {value!r}.")
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise InputError(f"{label} must be a number, got {value!r}.") from None
    if not math.isfinite(x):
        raise InputError(f"{label} must be a finite number.")
    return x


def dial_from_pv_yp(pv_cp: float, yp: float) -> Dict[int, float]:
    """Bingham PV/YP to 600 and 300 rpm dial readings: R600 = 2 PV + YP, R300 = PV + YP."""
    pv = _num(pv_cp, "PV")
    y = _num(yp, "YP")
    if pv <= 0:
        raise InputError("PV must be greater than 0 cP.")
    if y < 0:
        raise InputError("YP cannot be negative.")
    return {600: 2.0 * pv + y, 300: pv + y}


def rheology_params(readings: Mapping[Any, Any]) -> Dict[str, Any]:
    """Annular power-law n and K from dial readings.

    With 600, 300, 100 and 3 rpm available (API RP 13D 1995 annulus):
        n_a = 0.657 log10(R100 / R3)
        K_a = 5.11 R100 / 170.2^n_a           (dyne s^n / cm^2)
    With only 600 and 300 rpm (for example from PV/YP), fallback:
        n = 3.32 log10(R600 / R300)
        K = 5.11 R300 / 511^n                 (dyne s^n / cm^2)
    """
    r: Dict[int, float] = {}
    for key, val in readings.items():
        if val is None or (isinstance(val, str) and val.strip() == ""):
            continue
        try:
            rpm = int(key)
        except (TypeError, ValueError):
            raise InputError(f"Unknown viscometer speed {key!r}.") from None
        if rpm not in RPMS:
            raise InputError(f"Unsupported viscometer speed {rpm} rpm. Use 600, 300, 200, 100, 6, 3.")
        x = _num(val, f"{rpm} rpm reading")
        if x <= 0:
            raise InputError(f"{rpm} rpm reading must be greater than 0.")
        r[rpm] = x
    if 600 not in r or 300 not in r:
        raise InputError("600 and 300 rpm readings are required.")
    present = [rpm for rpm in RPMS if rpm in r]
    for hi, lo in zip(present, present[1:]):
        if r[lo] > r[hi]:
            raise InputError(
                f"Dial readings must not increase as speed drops: {lo} rpm ({r[lo]:g}) > {hi} rpm ({r[hi]:g})."
            )
    if r[600] <= r[300]:
        raise InputError("600 rpm reading must be greater than 300 rpm reading.")
    notes: List[str] = []
    if 100 in r and 3 in r:
        if r[100] <= r[3]:
            raise InputError("100 rpm reading must be greater than 3 rpm reading.")
        n = 0.657 * math.log10(r[100] / r[3])
        k_num, k_rate = r[100], SHEAR_100
        basis = "fann_100_3"
        notes.append("Annular n and K from 100 and 3 rpm readings (API RP 13D 1995 annulus).")
    else:
        n = 3.32 * math.log10(r[600] / r[300])
        k_num, k_rate = r[300], SHEAR_300
        basis = "fallback_600_300"
        missing = [str(x) for x in (100, 3) if x not in r]
        notes.append(
            "100/3 rpm readings not available (missing "
            + ", ".join(missing)
            + " rpm). Annular n and K use the 600/300 rpm power law; low-shear behavior is not represented."
        )
    if n > 2.0:
        raise InputError(f"Flow behavior index n = {n:.3f} is outside the range this model handles (n <= 2). Check the readings.")
    k = DIAL_TO_DYNE * k_num / k_rate ** n
    if n > 1.0:
        notes.append(f"n = {n:.3f} is above 1 (shear thickening). Typical drilling fluids have n < 1; check the readings.")
    return {"n": n, "K": k, "basis": basis, "readings": dict(sorted(r.items(), reverse=True)), "notes": notes}


def friction_factor(re: float, n: float) -> Dict[str, Any]:
    """API RP 13D (1995) annular Fanning friction factor and flow regime."""
    rc1 = 3470.0 - 1370.0 * n
    rc2 = 4270.0 - 1370.0 * n
    a = (math.log10(n) + 3.93) / 50.0
    b = (1.75 - math.log10(n)) / 7.0
    if re < rc1:
        return {"f": 24.0 / re, "regime": "laminar", "re_c1": rc1, "re_c2": rc2}
    if re > rc2:
        return {"f": a / re ** b, "regime": "turbulent", "re_c1": rc1, "re_c2": rc2}
    f1 = 24.0 / rc1
    f2 = a / rc2 ** b
    f = (re - rc1) / (rc2 - rc1) * (f2 - f1) + f1
    return {"f": f, "regime": "transitional", "re_c1": rc1, "re_c2": rc2}


def _validate_section(sec: Mapping[str, Any], idx: int) -> Dict[str, Any]:
    label = f"Section {idx + 1}"
    name = sec.get("name")
    name = str(name).strip() if name is not None and str(name).strip() else label
    if len(name) > 80:
        name = name[:80]
    hole = _num(sec.get("hole_id_in"), f"{label} hole/casing ID")
    pipe = _num(sec.get("pipe_od_in"), f"{label} pipe OD")
    length = _num(sec.get("length_ft"), f"{label} length")
    if hole <= 0:
        raise InputError(f"{label} hole/casing ID must be greater than 0.")
    if pipe < 0:
        raise InputError(f"{label} pipe OD cannot be negative.")
    if pipe >= hole:
        raise InputError(f"{label}: pipe OD ({pipe:g} in) must be smaller than hole/casing ID ({hole:g} in).")
    if length < 0:
        raise InputError(f"{label} length cannot be negative.")
    if hole > 60:
        raise InputError(f"{label} hole/casing ID of {hole:g} in is outside the supported range (60 in max).")
    return {"name": name, "hole_id_in": hole, "pipe_od_in": pipe, "length_ft": length}


def section_hydraulics(
    hole_id_in: float, pipe_od_in: float, length_ft: float, q_gpm: float, mw_ppg: float, n: float, k: float
) -> Dict[str, Any]:
    """Annular velocity, effective viscosity, Reynolds number, regime and pressure loss for one section."""
    d2, d1 = hole_id_in, pipe_od_in
    gap = d2 - d1
    va_fpm = VA_CONST * q_gpm / (d2 * d2 - d1 * d1)
    va_fps = va_fpm / 60.0
    if q_gpm == 0:
        return {
            "va_fpm": 0.0, "va_fps": 0.0, "shear_rate": 0.0, "mu_ea_cp": None, "re": 0.0,
            "f": None, "regime": "no flow", "re_c1": 3470.0 - 1370.0 * n, "re_c2": 4270.0 - 1370.0 * n,
            "dp_psi": 0.0, "grad_psi_ft": 0.0,
        }
    shear = 144.0 * va_fps / gap
    mu = 100.0 * k * shear ** (n - 1.0) * ((2.0 * n + 1.0) / (3.0 * n)) ** n
    re = RE_CONST * gap * va_fps * mw_ppg / mu
    if not (re > 0 and math.isfinite(re)):
        raise InputError(f"Flow rate {q_gpm:g} gpm is too small to evaluate. Use 0 for no flow.")
    ff = friction_factor(re, n)
    grad = ff["f"] * va_fps * va_fps * mw_ppg / (DP_CONST * gap)
    return {
        "va_fpm": va_fpm, "va_fps": va_fps, "shear_rate": shear, "mu_ea_cp": mu, "re": re,
        "f": ff["f"], "regime": ff["regime"], "re_c1": ff["re_c1"], "re_c2": ff["re_c2"],
        "dp_psi": grad * length_ft, "grad_psi_ft": grad,
    }


def normalize_case(case: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate a case dict and return a clean copy plus derived rheology."""
    if not isinstance(case, Mapping):
        raise InputError("Case must be an object.")
    mw = _num(case.get("mud_weight_ppg"), "Mud weight")
    q = _num(case.get("flow_rate_gpm"), "Flow rate")
    tvd = _num(case.get("tvd_ft"), "TVD")
    if mw <= 0:
        raise InputError("Mud weight must be greater than 0 ppg.")
    if mw > 25:
        raise InputError("Mud weight above 25 ppg is outside the supported range.")
    if q < 0:
        raise InputError("Flow rate cannot be negative.")
    if tvd <= 0:
        raise InputError("TVD must be greater than 0 ft.")
    rheo = case.get("rheology")
    if not isinstance(rheo, Mapping):
        raise InputError("Rheology is required: Fann readings or PV and YP.")
    notes: List[str] = []
    if rheo.get("fann") is not None:
        fann = rheo["fann"]
        if not isinstance(fann, Mapping):
            raise InputError("Fann readings must be a mapping of rpm to dial reading.")
        params = rheology_params(fann)
        source = "fann"
    elif rheo.get("pv_cp") is not None or rheo.get("yp") is not None:
        dials = dial_from_pv_yp(rheo.get("pv_cp"), rheo.get("yp"))
        params = rheology_params(dials)
        source = "pv_yp"
        notes.append(
            f"PV/YP converted to dial readings: R600 = 2 PV + YP = {dials[600]:g}, R300 = PV + YP = {dials[300]:g}."
        )
    else:
        raise InputError("Rheology is required: Fann readings or PV and YP.")
    notes.extend(params["notes"])
    secs = case.get("sections")
    if not isinstance(secs, Sequence) or isinstance(secs, (str, bytes)) or len(secs) == 0:
        raise InputError("At least one annular section is required.")
    if len(secs) > 200:
        raise InputError("At most 200 annular sections are supported.")
    sections = [_validate_section(s if isinstance(s, Mapping) else {}, i) for i, s in enumerate(secs)]
    frac = case.get("frac_emw_ppg")
    if frac is None or (isinstance(frac, str) and frac.strip() == ""):
        frac = None
    else:
        frac = _num(frac, "Fracture gradient")
        if not (0 < frac <= 30):
            raise InputError("Fracture gradient must be above 0 and at most 30 ppg EMW.")
    total_md = sum(s["length_ft"] for s in sections)
    if tvd > total_md + 1e-9:
        notes.append(
            f"TVD ({tvd:g} ft) exceeds total section length ({total_md:g} ft). Annular loss covers only the listed sections."
        )
    return {
        "mud_weight_ppg": mw, "flow_rate_gpm": q, "tvd_ft": tvd, "sections": sections,
        "rheology_source": source, "n": params["n"], "K": params["K"], "basis": params["basis"],
        "readings": params["readings"], "notes": notes, "frac_emw_ppg": frac,
    }


def evaluate(case: Mapping[str, Any], q_override: Optional[float] = None) -> Dict[str, Any]:
    """Full screening result for a case. See README for the case format."""
    c = normalize_case(case)
    q = c["flow_rate_gpm"] if q_override is None else _num(q_override, "Flow rate")
    if q < 0:
        raise InputError("Flow rate cannot be negative.")
    mw, tvd, n, k = c["mud_weight_ppg"], c["tvd_ft"], c["n"], c["K"]
    rows = []
    for s in c["sections"]:
        h = section_hydraulics(s["hole_id_in"], s["pipe_od_in"], s["length_ft"], q, mw, n, k)
        row = dict(s)
        row.update(h)
        rows.append(row)
    apl = sum(r["dp_psi"] for r in rows)
    notes = list(c["notes"])
    trans = [r["name"] for r in rows if r["regime"] == "transitional"]
    if trans:
        notes.append(
            "Transitional flow in: " + "; ".join(trans) + ". The 1995 transition friction factor is a straight-line "
            "blend; pressure loss can fall as rate rises across this band. Treat ECD here as uncertain."
        )
    hydro = HYDROSTATIC_CONST * mw * tvd
    ecd = mw + apl / (HYDROSTATIC_CONST * tvd)
    return {
        "inputs": {"mud_weight_ppg": mw, "flow_rate_gpm": q, "tvd_ft": tvd},
        "rheology": {"source": c["rheology_source"], "basis": c["basis"], "n": n, "K": k, "readings": c["readings"]},
        "sections": rows,
        "total_md_ft": sum(s["length_ft"] for s in c["sections"]),
        "apl_psi": apl,
        "hydrostatic_psi": hydro,
        "bhcp_psi": hydro + apl,
        "ecd_ppg": ecd,
        "esd_ppg": mw,
        "frac_emw_ppg": c["frac_emw_ppg"],
        "frac_margin_ppg": None if c["frac_emw_ppg"] is None else c["frac_emw_ppg"] - ecd,
        "warnings": density_checks(mw, ecd, c["frac_emw_ppg"]),
        "notes": notes,
    }


def density_checks(mw: float, ecd: float, frac: Optional[float]) -> List[Dict[str, str]]:
    """Plain warnings when ESD (static mud weight) or ECD is implausible or reaches the fracture gradient."""
    out: List[Dict[str, str]] = []
    if ecd > ECD_MAX_PLAUSIBLE_PPG:
        out.append({"code": "ecd_implausible", "message": (
            f"ECD of {ecd:.2f} ppg is above {ECD_MAX_PLAUSIBLE_PPG:g} ppg, heavier than any drilling fluid in use. "
            "Check the flow rate, the hole and pipe sizes, and the rheology.")})
    elif ecd - mw > ECD_RISE_FLAG_PPG:
        out.append({"code": "ecd_large_rise", "message": (
            f"Annular friction adds {ecd - mw:.2f} ppg to the mud weight, more than {ECD_RISE_FLAG_PPG:g} ppg. "
            "That is unusual for a drilling annulus; check the flow rate and the annulus sizes.")})
    if frac is not None:
        if mw >= frac:
            out.append({"code": "esd_over_frac", "message": (
                f"Static mud weight (ESD) {mw:.2f} ppg is at or above the fracture gradient {frac:.2f} ppg. "
                "Losses are expected even with the pumps off.")})
        elif ecd > frac:
            out.append({"code": "ecd_over_frac", "message": (
                f"ECD {ecd:.2f} ppg exceeds the fracture gradient {frac:.2f} ppg by {ecd - frac:.2f} ppg. "
                "Losses are likely while circulating at this rate.")})
        elif frac - ecd < FRAC_NEAR_PPG:
            out.append({"code": "ecd_near_frac", "message": (
                f"ECD {ecd:.2f} ppg is within {FRAC_NEAR_PPG:g} ppg of the fracture gradient {frac:.2f} ppg.")})
    return out


def default_sweep_rates(q_gpm: float, steps: int = 41) -> List[float]:
    """0 to max(1.5 Q, 100) gpm in equal steps."""
    top = max(1.5 * q_gpm, 100.0)
    return [top * i / (steps - 1) for i in range(steps)]


def ecd_sweep(case: Mapping[str, Any], rates: Optional[Sequence[float]] = None) -> List[Dict[str, float]]:
    """ECD and APL across a list of flow rates, other inputs held fixed."""
    if rates is None:
        rates = default_sweep_rates(normalize_case(case)["flow_rate_gpm"])
    out = []
    for q in rates:
        r = evaluate(case, q_override=q)
        trans = any(sec["regime"] == "transitional" for sec in r["sections"])
        out.append({
            "q_gpm": r["inputs"]["flow_rate_gpm"], "apl_psi": r["apl_psi"], "ecd_ppg": r["ecd_ppg"],
            "transitional": trans,
        })
    return out


def sweep_dips(sweep: Sequence[Mapping[str, Any]]) -> List[Dict[str, float]]:
    """Rate ranges where computed ECD falls as flow rate rises (a transitional-flow artifact of the 1995 model).

    Returns a list of {"q_from", "q_to", "ecd_from", "ecd_to"} covering each run of decreasing ECD.
    """
    out: List[Dict[str, float]] = []
    i = 1
    while i < len(sweep):
        if sweep[i]["ecd_ppg"] < sweep[i - 1]["ecd_ppg"]:
            j = i
            while j + 1 < len(sweep) and sweep[j + 1]["ecd_ppg"] < sweep[j]["ecd_ppg"]:
                j += 1
            out.append({
                "q_from": sweep[i - 1]["q_gpm"], "q_to": sweep[j]["q_gpm"],
                "ecd_from": sweep[i - 1]["ecd_ppg"], "ecd_to": sweep[j]["ecd_ppg"],
            })
            i = j + 1
        else:
            i += 1
    return out


# Example data: Permian-style horizontal well, water-based mud, tapered 5 in x 4-1/2 in drill string.
# Intermediate casing is 9-5/8 in 40 lb/ft (8.835 in ID), the casing an 8-1/2 in hole is drilled
# below. Illustrative only, not a real well design.
EXAMPLE_CASE: Dict[str, Any] = {
    "label": "Example data",
    "mud_weight_ppg": 9.8,
    "flow_rate_gpm": 550.0,
    "tvd_ft": 9800.0,
    "rheology": {"fann": {"600": 52, "300": 33, "200": 25, "100": 17, "6": 6, "3": 5}},
    "sections": [
        {"name": "Casing 8.835 in ID x 5 in DP", "hole_id_in": 8.835, "pipe_od_in": 5.0, "length_ft": 9200.0},
        {"name": "Open hole 8.5 in x 5 in DP (curve)", "hole_id_in": 8.5, "pipe_od_in": 5.0, "length_ft": 1400.0},
        {"name": "Open hole 8.5 in x 4.5 in DP (lateral)", "hole_id_in": 8.5, "pipe_od_in": 4.5, "length_ft": 8500.0},
        {"name": "Open hole 8.5 in x 6.75 in BHA", "hole_id_in": 8.5, "pipe_od_in": 6.75, "length_ft": 280.0},
    ],
}
