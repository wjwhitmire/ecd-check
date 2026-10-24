"""Command line interface.

Examples:
    ecd-check --example
    ecd-check case.json
    ecd-check --sections sections.csv --mw 9.8 --q 550 --tvd 9800 --fann 600=52,300=33,100=17,3=5
    ecd-check --sections sections.csv --mw 9.8 --q 550 --tvd 9800 --pv 19 --yp 14 --sweep
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from typing import Any, Dict, List, Optional

from .core import EXAMPLE_CASE, InputError, ecd_sweep, evaluate, sweep_dips
from .parse import parse_sections_text

MAX_BYTES = 5 * 1024 * 1024


def _read_text(path: str) -> str:
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        raise InputError(f"Cannot open {path}: {exc.strerror}.") from None
    if size > MAX_BYTES:
        raise InputError(f"{path} is larger than 5 MB.")
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return fh.read()
    except UnicodeDecodeError:
        raise InputError(f"{path} is not UTF-8 text. Save it as CSV or JSON text.") from None
    except OSError as exc:
        raise InputError(f"Cannot open {path}: {exc.strerror}.") from None


def _parse_fann(readings: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for part in readings.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise InputError(f"Fann reading {part!r} must look like 600=52.")
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()  # type: ignore[assignment]
    return out


def build_case(args: argparse.Namespace) -> Dict[str, Any]:
    if args.example:
        case = copy.deepcopy(EXAMPLE_CASE)
    elif args.case:
        try:
            case = json.loads(_read_text(args.case))
        except json.JSONDecodeError as exc:
            raise InputError(f"{args.case} is not valid JSON (line {exc.lineno}).") from None
        if not isinstance(case, dict):
            raise InputError("Case JSON must be an object.")
    else:
        if not args.sections:
            raise InputError("Give a case JSON file, --sections with fluid inputs, or --example.")
        case = {"sections": parse_sections_text(_read_text(args.sections))}
    if args.mw is not None:
        case["mud_weight_ppg"] = args.mw
    if args.q is not None:
        case["flow_rate_gpm"] = args.q
    if args.tvd is not None:
        case["tvd_ft"] = args.tvd
    if args.frac is not None:
        case["frac_emw_ppg"] = args.frac
    if args.fann:
        case["rheology"] = {"fann": _parse_fann(args.fann)}
    elif args.pv is not None or args.yp is not None:
        case["rheology"] = {"pv_cp": args.pv, "yp": args.yp}
    if args.sections and (args.case or args.example):
        case["sections"] = parse_sections_text(_read_text(args.sections))
    return case


def format_report(res: Dict[str, Any]) -> str:
    lines: List[str] = []
    rh = res["rheology"]
    lines.append("ECD Check (screening only, not a full hydraulics program)")
    lines.append(f"Rheology: n = {rh['n']:.4f}, K = {rh['K']:.4f} dyne s^n/cm^2 ({rh['basis']})")
    hdr = f"{'Section':<40} {'Va ft/min':>10} {'Re':>9} {'Regime':>13} {'dP psi':>9}"
    lines.append(hdr)
    lines.append("-" * len(hdr))
    for s in res["sections"]:
        lines.append(
            f"{s['name'][:40]:<40} {s['va_fpm']:>10.1f} {s['re']:>9.0f} {s['regime']:>13} {s['dp_psi']:>9.1f}"
        )
    lines.append("-" * len(hdr))
    lines.append(f"Annular pressure loss: {res['apl_psi']:.1f} psi")
    lines.append(f"Hydrostatic at TVD:    {res['hydrostatic_psi']:.1f} psi")
    lines.append(f"BHCP:                  {res['bhcp_psi']:.1f} psi")
    lines.append(f"ECD:                   {res['ecd_ppg']:.3f} ppg")
    if res["frac_emw_ppg"] is not None:
        lines.append(f"Frac gradient:         {res['frac_emw_ppg']:.3f} ppg EMW, margin {res['frac_margin_ppg']:+.3f} ppg")
    for w in res["warnings"]:
        lines.append(f"CHECK: {w['message']}")
    for note in res["notes"]:
        lines.append(f"Note: {note}")
    return "\n".join(lines)


def dip_messages(dips: List[Dict[str, float]]) -> List[str]:
    """Plain-language warning for each rate range where computed ECD falls as rate rises."""
    return [
        f"Computed ECD falls from {d['ecd_from']:.2f} to {d['ecd_to']:.2f} ppg as rate rises from "
        f"{d['q_from']:.0f} to {d['q_to']:.0f} gpm. This is an artifact of the 1995 transitional-flow blend, "
        "not a real ECD reduction. Do not raise rate to lower ECD on the strength of this curve."
        for d in dips
    ]


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="ecd-check", description="Annular hydraulics screening (API RP 13D 1995 power law).")
    p.add_argument("case", nargs="?", help="case JSON file")
    p.add_argument("--example", action="store_true", help="run the built-in example data")
    p.add_argument("--sections", help="CSV/TSV of name, hole_id_in, pipe_od_in, length_ft")
    p.add_argument("--mw", type=float, help="mud weight, ppg")
    p.add_argument("--q", type=float, help="flow rate, gpm")
    p.add_argument("--tvd", type=float, help="TVD of point of interest, ft")
    p.add_argument("--frac", type=float, help="fracture gradient at TVD, ppg EMW (optional; adds a margin)")
    p.add_argument("--fann", help="dial readings, e.g. 600=52,300=33,100=17,3=5")
    p.add_argument("--pv", type=float, help="plastic viscosity, cP")
    p.add_argument("--yp", type=float, help="yield point, lbf/100ft2")
    p.add_argument("--sweep", action="store_true", help="also print ECD vs flow rate")
    p.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = p.parse_args(argv)
    try:
        case = build_case(args)
        res = evaluate(case)
        sweep = ecd_sweep(case) if args.sweep else None
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        out = {"result": res}
        if sweep is not None:
            out["sweep"] = sweep
            out["sweep_dips"] = sweep_dips(sweep)
        print(json.dumps(out, indent=2))
    else:
        print(format_report(res))
        if sweep is not None:
            print()
            print(f"{'Q gpm':>8} {'APL psi':>9} {'ECD ppg':>8}  Flow")
            for row in sweep:
                flag = "transitional" if row["transitional"] else ""
                print(f"{row['q_gpm']:>8.0f} {row['apl_psi']:>9.1f} {row['ecd_ppg']:>8.3f}  {flag}")
            for line in dip_messages(sweep_dips(sweep)):
                print(f"Note: {line}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
