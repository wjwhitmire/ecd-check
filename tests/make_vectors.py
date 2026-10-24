"""Generate tests/vectors.json from the Python library. Run: python tests/make_vectors.py"""

import copy
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from ecd_check import EXAMPLE_CASE, InputError, ecd_sweep, evaluate, parse_sections_text, sweep_dips  # noqa: E402


def base(**over):
    c = copy.deepcopy(EXAMPLE_CASE)
    c.pop("label", None)
    c.update(over)
    return c


def single(hole, pipe, length, q, mw, tvd, rheo):
    return {
        "mud_weight_ppg": mw, "flow_rate_gpm": q, "tvd_ft": tvd, "rheology": rheo,
        "sections": [{"name": "S1", "hole_id_in": hole, "pipe_od_in": pipe, "length_ft": length}],
    }


CASES = [
    ("example", base()),
    ("example_zero_flow", base(flow_rate_gpm=0)),
    ("example_pv_yp", base(rheology={"pv_cp": 19, "yp": 14})),
    ("example_fann_600_300_only", base(rheology={"fann": {"600": 52, "300": 33}})),
    ("laminar_hand", single(8.5, 5.0, 1000, 300, 10.0, 1000, {"fann": {"600": 50, "300": 35, "100": 20, "3": 5}})),
    ("turbulent_hand", single(6.276, 5.0, 1000, 500, 12.0, 1000, {"fann": {"600": 30, "300": 18, "100": 10, "3": 2}})),
    ("transitional", single(8.5, 5.0, 10000, 600, 9.8, 9800, {"fann": {"600": 52, "300": 33, "100": 17, "3": 5}})),
    ("open_hole_no_pipe", single(8.5, 0.0, 500, 400, 10.0, 9000, {"fann": {"600": 40, "300": 25, "100": 12, "3": 3}})),
    ("heavy_oil_mud", single(6.125, 4.0, 12000, 280, 14.5, 11500, {"fann": {"600": 70, "300": 42, "200": 32, "100": 21, "6": 8, "3": 7}})),
    ("shear_thickening_warn", single(8.5, 5.0, 1000, 300, 10.0, 1000, {"fann": {"600": 60, "300": 40, "100": 30, "3": 0.5}})),
    ("frac_margin_ok", base(frac_emw_ppg=12.5)),
    ("frac_near", base(frac_emw_ppg=10.7)),
    ("frac_exceeded", base(frac_emw_ppg=10.3)),
    ("esd_over_frac", base(frac_emw_ppg=9.5)),
    ("ecd_large_rise", single(6.276, 5.0, 9000, 500, 12.0, 6000, {"fann": {"600": 30, "300": 18, "100": 10, "3": 2}})),
    ("ecd_implausible", single(6.276, 5.0, 30000, 900, 16.0, 30000, {"fann": {"600": 90, "300": 55, "100": 25, "3": 6}})),
    ("err_frac_zero", base(frac_emw_ppg=0)),
    ("err_frac_text", base(frac_emw_ppg="abc")),
    ("err_pipe_ge_hole", base(sections=[{"name": "x", "hole_id_in": 5, "pipe_od_in": 5, "length_ft": 100}])),
    ("err_negative_mw", base(mud_weight_ppg=-1)),
    ("err_negative_q", base(flow_rate_gpm=-10)),
    ("err_negative_length", base(sections=[{"name": "x", "hole_id_in": 8.5, "pipe_od_in": 5, "length_ft": -1}])),
    ("err_bad_dials", base(rheology={"fann": {"600": 30, "300": 40}})),
    ("err_tiny_flow", base(flow_rate_gpm=1e-300)),
    ("err_huge_dials", base(rheology={"fann": {"600": 1e308, "300": 1e307, "100": 1e306, "3": 1}})),
]


PARSE_CASES = [
    ("header_csv", "name,hole_id_in,pipe_od_in,length_ft\nCasing,8.835,5,9200\nOH,8.5,4.5,8500\n"),
    ("tabs_extra_cols_blank_lines", "Section\tHole ID\tPipe OD\tLength\tNote\n\nA\t8.5\t5\t1000\tx\r\n\nB\t8.5\t6.75\t200\ty\n"),
    ("no_header_three_cols", "8.5,5,1000\n8.5,4.5,500\n"),
    ("err_quoted_comma_unsupported", '"Casing, 9-5/8",8.835,5,9200\n'),
    ("comment_lines", "# geometry\nname,hole,pipe,length\nA,8.5,5,100\n"),
    ("err_bad_number", "name,hole,pipe,length\nA,8.5,abc,100\n"),
    ("err_nan", "name,hole,pipe,length\nA,8.5,NaN,100\n"),
    ("err_bad_header", "foo,bar\n1,2\n"),
    ("err_empty", "\n\n"),
    ("err_header_only", "name,hole,pipe,length\n"),
    ("bom_no_header", "\ufeff8.5,5,100\n"),
]


def main():
    out = {"generator": "tests/make_vectors.py", "cases": [], "parse": []}
    for name, text in PARSE_CASES:
        try:
            out["parse"].append({"name": name, "text": text, "rows": parse_sections_text(text)})
        except InputError as exc:
            out["parse"].append({"name": name, "text": text, "error": str(exc)})
    for name, case in CASES:
        try:
            res = evaluate(case)
        except InputError as exc:
            out["cases"].append({"name": name, "input": case, "error": str(exc)})
            continue
        entry = {"name": name, "input": case, "result": res}
        if name in ("example", "transitional", "example_pv_yp"):
            entry["sweep"] = ecd_sweep(case)
            entry["sweep_dips"] = sweep_dips(entry["sweep"])
        out["cases"].append(entry)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vectors.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"wrote {len(out['cases'])} vectors to tests/vectors.json")


if __name__ == "__main__":
    main()
