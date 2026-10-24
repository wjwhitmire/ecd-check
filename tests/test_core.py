import copy
import json
import math
import os

import pytest

from ecd_check import (
    EXAMPLE_CASE,
    InputError,
    dial_from_pv_yp,
    ecd_sweep,
    evaluate,
    friction_factor,
    parse_sections_text,
    rheology_params,
    section_hydraulics,
)
from ecd_check.cli import main


def case_with(**over):
    c = copy.deepcopy(EXAMPLE_CASE)
    c.update(over)
    return c


# ---------------------------------------------------------------- hand-computed laminar case
# D2 = 8.5 in, D1 = 5 in, L = 1000 ft, Q = 300 gpm, MW = 10 ppg, R100 = 20, R3 = 5.
#   n   = 0.657 log10(20/5)            = 0.657 * 0.602060          = 0.395553
#   K   = 5.11 * 20 / 170.2^0.395553   = 102.2 / 7.62891           = 13.3964 dyne s^n/cm^2
#   Va  = 0.408 * 300 / (72.25 - 25)   = 122.4 / 47.25             = 2.590476 ft/s (155.43 ft/min)
#   gam = 144 * 2.590476 / 3.5                                     = 106.5796 1/s
#   mu  = 100 K gam^(n-1) ((2n+1)/(3n))^n
#       = 1339.64 * 106.5796^-0.604447 * 1.509494^0.395553         = 93.7755 cP
#   Re  = 928 * 3.5 * 2.590476 * 10 / 93.7755                      = 897.23  (< 3470 - 1370 n = 2928.1, laminar)
#   f   = 24 / 897.23                                              = 0.0267489
#   dP  = f Va^2 MW / (25.81 * 3.5) * 1000                         = 19.870 psi
def test_laminar_hand_case():
    n = 0.657 * math.log10(20 / 5)
    k = 5.11 * 20 / 170.2 ** n
    assert n == pytest.approx(0.395553, abs=1e-6)
    assert k == pytest.approx(13.3964, abs=1e-3)
    r = section_hydraulics(8.5, 5.0, 1000.0, 300.0, 10.0, n, k)
    assert r["va_fpm"] == pytest.approx(155.4286, abs=1e-3)
    assert r["shear_rate"] == pytest.approx(106.5796, abs=1e-3)
    assert r["mu_ea_cp"] == pytest.approx(93.7755, abs=1e-3)
    assert r["re"] == pytest.approx(897.23, abs=0.01)
    assert r["regime"] == "laminar"
    assert r["f"] == pytest.approx(0.0267489, rel=1e-5)
    assert r["dp_psi"] == pytest.approx(19.870, abs=1e-3)


# ---------------------------------------------------------------- hand-computed turbulent case
# D2 = 6.276 in, D1 = 5 in, L = 1000 ft, Q = 500 gpm, MW = 12 ppg, R100 = 10, R3 = 2.
#   n   = 0.657 log10(5)                    = 0.459223
#   K   = 5.11 * 10 / 170.2^0.459223        = 4.82961
#   Va  = 0.408 * 500 / (39.388176 - 25)    = 14.178309 ft/s (850.70 ft/min)
#   gam = 144 * 14.178309 / 1.276           = 1600.06 1/s
#   mu  = 10.4047 cP
#   Re  = 928 * 1.276 * 14.178309 * 12 / 10.4047 = 19363.1 (> 4270 - 1370 n = 3640.9, turbulent)
#   a   = (log10 n + 3.93)/50 = 0.0718405 ; b = (1.75 - log10 n)/7 = 0.2982823
#   f   = a / Re^b                          = 0.00378129
#   dP  = f Va^2 MW / (25.81 * 1.276) * 1000 = 276.97 psi
def test_turbulent_hand_case():
    n = 0.657 * math.log10(5)
    k = 5.11 * 10 / 170.2 ** n
    r = section_hydraulics(6.276, 5.0, 1000.0, 500.0, 12.0, n, k)
    assert r["va_fpm"] == pytest.approx(850.6985, abs=1e-3)
    assert r["mu_ea_cp"] == pytest.approx(10.4047, abs=1e-3)
    assert r["re"] == pytest.approx(19363.1, abs=0.5)
    assert r["regime"] == "turbulent"
    a = (math.log10(n) + 3.93) / 50
    b = (1.75 - math.log10(n)) / 7
    assert a == pytest.approx(0.0718405, abs=1e-6)
    assert b == pytest.approx(0.2982823, abs=1e-6)
    assert r["f"] == pytest.approx(0.00378129, rel=1e-5)
    assert r["dp_psi"] == pytest.approx(276.97, abs=0.01)


def test_transition_interpolates_between_endpoints():
    n = 0.5
    rc1, rc2 = 3470 - 1370 * n, 4270 - 1370 * n
    a = (math.log10(n) + 3.93) / 50
    b = (1.75 - math.log10(n)) / 7
    f1, f2 = 24 / rc1, a / rc2 ** b
    mid = friction_factor((rc1 + rc2) / 2, n)
    assert mid["regime"] == "transitional"
    assert mid["f"] == pytest.approx((f1 + f2) / 2, rel=1e-12)
    assert friction_factor(rc1 - 1e-6, n)["regime"] == "laminar"
    assert friction_factor(rc2 + 1e-6, n)["regime"] == "turbulent"
    # continuous at both boundaries
    assert friction_factor(rc1, n)["f"] == pytest.approx(f1, rel=1e-9)
    assert friction_factor(rc2, n)["f"] == pytest.approx(f2, rel=1e-9)


# ---------------------------------------------------------------- unit sanity
def test_zero_flow_ecd_equals_mw():
    r = evaluate(case_with(flow_rate_gpm=0))
    assert r["apl_psi"] == 0.0
    assert r["ecd_ppg"] == pytest.approx(EXAMPLE_CASE["mud_weight_ppg"], abs=1e-12)
    assert r["bhcp_psi"] == pytest.approx(r["hydrostatic_psi"])
    assert all(s["regime"] == "no flow" for s in r["sections"])


def test_hydrostatic_and_ecd_definitions():
    r = evaluate(EXAMPLE_CASE)
    mw, tvd = EXAMPLE_CASE["mud_weight_ppg"], EXAMPLE_CASE["tvd_ft"]
    assert r["hydrostatic_psi"] == pytest.approx(0.052 * mw * tvd)
    assert r["ecd_ppg"] == pytest.approx(mw + r["apl_psi"] / (0.052 * tvd))
    assert r["bhcp_psi"] == pytest.approx(0.052 * r["ecd_ppg"] * tvd)
    assert r["apl_psi"] == pytest.approx(sum(s["dp_psi"] for s in r["sections"]))


def test_unit_constants_derived_from_si():
    # Annular velocity: gpm -> ft3/min over annulus area in ft2.
    gal_ft3 = 231.0 / 1728.0
    va_const = gal_ft3 * 144.0 * 4.0 / math.pi
    assert va_const == pytest.approx(24.51, abs=0.01)
    assert 0.408 * 60 == pytest.approx(24.48)
    # Reynolds: ppg->kg/m3, in->m, ft/s->m/s, cP->Pa s.
    ppg = 0.45359237 / (gal_ft3 * 0.3048 ** 3)
    re_const = ppg * 0.0254 * 0.3048 / 1e-3
    assert re_const == pytest.approx(928, rel=1e-3)
    # Fanning dP/L = 2 f rho v^2 / Dh, in psi/ft with ppg, ft/s, in.
    pa_per_m = 2 * ppg * 0.3048 ** 2 / 0.0254
    psi_per_ft = pa_per_m * 0.3048 / 6894.757293168
    assert 1 / psi_per_ft == pytest.approx(25.81, abs=0.01)
    # Hydrostatic: ppg -> psi/ft.
    assert 7.48051948 / 144 == pytest.approx(0.052, abs=1e-4)


# ---------------------------------------------------------------- monotonic ECD in Q
def _single_section(hole, pipe, fann):
    return {
        "mud_weight_ppg": 10.0, "flow_rate_gpm": 300.0, "tvd_ft": 10000.0,
        "rheology": {"fann": fann},
        "sections": [{"name": "s", "hole_id_in": hole, "pipe_od_in": pipe, "length_ft": 10000.0}],
    }


def test_monotonic_ecd_laminar_band():
    case = _single_section(8.5, 4.5, {"600": 60, "300": 40, "100": 22, "3": 8})
    sweep = ecd_sweep(case, [10 * i for i in range(0, 61)])
    assert all(s["transitional"] is False for s in sweep)
    assert all(evaluate(case, q)["sections"][0]["regime"] in ("laminar", "no flow") for q in (0, 300, 600))
    ecd = [s["ecd_ppg"] for s in sweep]
    assert all(b > a for a, b in zip(ecd, ecd[1:]))


def test_monotonic_ecd_turbulent_band():
    case = _single_section(6.276, 5.0, {"600": 30, "300": 18, "100": 9, "3": 2})
    rates = [400 + 10 * i for i in range(0, 41)]
    assert all(evaluate(case, q)["sections"][0]["regime"] == "turbulent" for q in rates)
    ecd = [s["ecd_ppg"] for s in ecd_sweep(case, rates)]
    assert all(b > a for a, b in zip(ecd, ecd[1:]))


def test_monotonic_ecd_example_outside_transition():
    sweep = ecd_sweep(EXAMPLE_CASE)
    clean = [s for s in sweep if not s["transitional"]]
    assert len(clean) > 10
    # Strictly increasing along runs that contain no transitional section.
    runs, cur = [], []
    for s in sweep:
        if s["transitional"]:
            if cur:
                runs.append(cur)
            cur = []
        else:
            cur.append(s["ecd_ppg"])
    runs.append(cur)
    for run in runs:
        assert all(b > a for a, b in zip(run, run[1:]))


# ---------------------------------------------------------------- PV/YP conversion
def test_pv_yp_to_dial():
    assert dial_from_pv_yp(18, 12) == {600: 48.0, 300: 30.0}


def test_pv_yp_case_uses_600_300_power_law_and_says_so():
    r = evaluate(case_with(rheology={"pv_cp": 18, "yp": 12}))
    n = 3.32 * math.log10(48 / 30)
    k = 5.11 * 30 / 511 ** n
    assert r["rheology"]["basis"] == "fallback_600_300"
    assert r["rheology"]["n"] == pytest.approx(n, rel=1e-12)
    assert r["rheology"]["K"] == pytest.approx(k, rel=1e-12)
    assert any("600/300" in s for s in r["notes"])
    assert any("R600 = 2 PV + YP = 48" in s for s in r["notes"])


def test_fann_without_low_shear_falls_back():
    p = rheology_params({"600": 48, "300": 30})
    assert p["basis"] == "fallback_600_300"


def test_fann_annulus_params():
    p = rheology_params({600: 52, 300: 33, 200: 25, 100: 17, 6: 6, 3: 5})
    assert p["n"] == pytest.approx(0.657 * math.log10(17 / 5), rel=1e-12)
    assert p["K"] == pytest.approx(5.11 * 17 / 170.2 ** p["n"], rel=1e-12)
    assert p["basis"] == "fann_100_3"


# ---------------------------------------------------------------- bad input
@pytest.mark.parametrize(
    "mutate, msg",
    [
        (lambda c: c["sections"][0].update(pipe_od_in=9.0), "must be smaller"),
        (lambda c: c["sections"][0].update(pipe_od_in=c["sections"][0]["hole_id_in"]), "must be smaller"),
        (lambda c: c["sections"][1].update(length_ft=-5), "length cannot be negative"),
        (lambda c: c["sections"][1].update(pipe_od_in=-1), "pipe OD cannot be negative"),
        (lambda c: c["sections"][1].update(hole_id_in="abc"), "must be a number"),
        (lambda c: c.update(mud_weight_ppg=-9.8), "Mud weight"),
        (lambda c: c.update(mud_weight_ppg=float("nan")), "finite"),
        (lambda c: c.update(flow_rate_gpm=-1), "Flow rate cannot be negative"),
        (lambda c: c.update(tvd_ft=0), "TVD"),
        (lambda c: c.update(sections=[]), "At least one"),
        (lambda c: c.update(rheology={"fann": {"600": 30, "300": 40, "100": 20, "3": 5}}), "must not increase"),
        (lambda c: c.update(rheology={"fann": {"600": 30, "300": -1}}), "greater than 0"),
        (lambda c: c.update(rheology={"fann": {"300": 30}}), "600 and 300"),
        (lambda c: c.update(rheology={"fann": {"600": 50, "300": 30, "100": 5, "3": 5}}), "100 rpm reading must be greater"),
        (lambda c: c.update(rheology={"pv_cp": -5, "yp": 10}), "PV"),
        (lambda c: c.update(rheology={"pv_cp": 18, "yp": -1}), "YP"),
        (lambda c: c.update(rheology={}), "Rheology"),
    ],
)
def test_bad_input(mutate, msg):
    c = copy.deepcopy(EXAMPLE_CASE)
    mutate(c)
    with pytest.raises(InputError, match=msg):
        evaluate(c)


# ---------------------------------------------------------------- parsing and CLI
def test_parse_sections_header_tabs_extra_columns():
    text = "name\thole_id_in\tpipe_od_in\tlength_ft\tnote\n\nA\t8.5\t5\t1000\tx\nB\t8.5\t6.75\t200\ty\n"
    rows = parse_sections_text(text)
    assert rows == [
        {"name": "A", "hole_id_in": 8.5, "pipe_od_in": 5.0, "length_ft": 1000.0},
        {"name": "B", "hole_id_in": 8.5, "pipe_od_in": 6.75, "length_ft": 200.0},
    ]


def test_parse_sections_no_header():
    rows = parse_sections_text("8.5,5,1000\n8.5,4.5,500\n")
    assert rows[1]["pipe_od_in"] == 4.5 and rows[0]["name"] == "Section 1"


def test_parse_sections_bad_number():
    with pytest.raises(InputError, match="Line 3: pipe OD 'NaNx'"):
        parse_sections_text("name,hole,pipe,length\nA,8.5,5,100\nB,8.5,NaNx,100\n")


def test_parse_sections_nan_rejected():
    with pytest.raises(InputError, match="not a number"):
        parse_sections_text("name,hole,pipe,length\nA,8.5,nan,100\n")


def test_cli_example(capsys):
    assert main(["--example"]) == 0
    out = capsys.readouterr().out
    assert "ECD:" in out and "screening" in out


def test_cli_files(tmp_path, capsys):
    sec = tmp_path / "s.csv"
    sec.write_text("name,hole_id_in,pipe_od_in,length_ft\nOH,8.5,5,10000\n")
    assert main(["--sections", str(sec), "--mw", "10", "--q", "400", "--tvd", "9000", "--pv", "18", "--yp", "12", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["result"]["rheology"]["basis"] == "fallback_600_300"
    assert main(["--sections", str(sec), "--mw", "10", "--q", "400", "--tvd", "9000"]) == 2
    assert "Rheology" in capsys.readouterr().err


def test_vectors_match_library():
    path = os.path.join(os.path.dirname(__file__), "vectors.json")
    with open(path, encoding="utf-8") as fh:
        vec = json.load(fh)
    for v in vec["cases"]:
        if "error" in v:
            with pytest.raises(InputError):
                evaluate(v["input"])
            continue
        r = evaluate(v["input"])
        assert r["ecd_ppg"] == pytest.approx(v["result"]["ecd_ppg"], rel=1e-12)


# ---------------------------------------------------------------- review fixes (regression tests)
# Independent check of the example well, computed by a reviewer from the 1995 equations without the package:
#   n_a = 0.349182, K_a = 14.44973, APL = 364.6184 psi, ECD = 10.515499 ppg.
def test_example_matches_independent_reference():
    r = evaluate(EXAMPLE_CASE)
    assert r["rheology"]["n"] == pytest.approx(0.349182, abs=1e-6)
    assert r["rheology"]["K"] == pytest.approx(14.44973, abs=1e-4)
    assert r["apl_psi"] == pytest.approx(364.6184, abs=1e-3)
    assert r["ecd_ppg"] == pytest.approx(10.515499, abs=1e-6)


def test_tiny_flow_is_input_error_not_crash():
    with pytest.raises(InputError, match="too small"):
        evaluate(case_with(flow_rate_gpm=1e-300))


def test_huge_dials_rejected_before_overflow():
    with pytest.raises(InputError, match="outside the range"):
        evaluate(case_with(rheology={"fann": {"600": 1e308, "300": 1e307, "100": 1e306, "3": 1}}))


def test_parse_strips_bom_without_header():
    rows = parse_sections_text("﻿8.5,5,100\n")
    assert rows == [{"name": "Section 1", "hole_id_in": 8.5, "pipe_od_in": 5.0, "length_ft": 100.0}]


def test_cli_directory_and_binary_file_are_clean_errors(tmp_path, capsys):
    assert main([str(tmp_path)]) == 2
    assert "Cannot open" in capsys.readouterr().err
    b = tmp_path / "b.json"
    b.write_bytes(b"\xff\xfe\x00garbage")
    assert main([str(b)]) == 2
    assert "not UTF-8" in capsys.readouterr().err


def test_sweep_dips_flag_example_transition_dip():
    from ecd_check import sweep_dips
    sw = ecd_sweep(EXAMPLE_CASE)
    dips = sweep_dips(sw)
    assert dips, "example sweep has a transitional ECD dip that must be reported"
    for d in dips:
        assert d["ecd_to"] < d["ecd_from"] and d["q_to"] > d["q_from"]
    # every dip lies inside a transitional rate
    trans_q = [p["q_gpm"] for p in sw if p["transitional"]]
    assert all(min(trans_q) <= d["q_to"] <= max(trans_q) + 1e-9 for d in dips)
    assert sweep_dips([{"q_gpm": 0, "ecd_ppg": 9.8}, {"q_gpm": 1, "ecd_ppg": 9.9}]) == []


def test_cli_sweep_prints_dip_warning(capsys):
    assert main(["--example", "--sweep"]) == 0
    out = capsys.readouterr().out
    assert "transitional" in out and "not a real ECD reduction" in out


def test_csv_export_neutralizes_formula_injection():
    import re
    import subprocess  # test-only: runs the JS core under node; library code has no subprocess use
    import shutil
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = (
        "const fs=require('fs'),vm=require('vm');"
        "const h=fs.readFileSync(process.argv[1],'utf8');"
        "const m=h.match(/<script id=\"core\">([\\s\\S]*?)<\\/script>/);"
        "const c=vm.createContext({Math,Number,String,Object,Array,Error,isFinite,parseInt,JSON});"
        "vm.runInContext(m[1]+';globalThis.o={evaluate,resultsCsv,EXAMPLE_CASE};',c);"
        "const out=[];for(const nm of ['=CMD|\"/C calc\"!A0','+1+1','-2+3','@SUM(A1)','\\t=1']){"
        "const b=JSON.parse(JSON.stringify(c.o.EXAMPLE_CASE));b.sections[0].name=nm;"
        "out.push(c.o.resultsCsv(c.o.evaluate(b)).split('\\n')[1]);}"
        "console.log(JSON.stringify(out));"
    )
    res = subprocess.run([node, "-e", js, os.path.join(root, "web", "app.html")], capture_output=True, text=True, check=True)
    for line in json.loads(res.stdout):
        first = line[1:] if line.startswith('"') else line
        assert first.startswith("'"), line
        assert not re.match(r"^[=+\-@]", first)


def test_bad_number_in_first_row_names_the_line():
    # used to say "Could not read the header row", which hid the real problem (a bad number)
    from ecd_check.parse import parse_sections_text

    with pytest.raises(InputError, match="Line 1 is neither a header row"):
        parse_sections_text("Csg,8.835,abc,9200\n")


def test_frac_margin_and_density_warnings():
    import copy

    case = copy.deepcopy(EXAMPLE_CASE)
    r = evaluate(case)
    assert r["frac_margin_ppg"] is None and r["warnings"] == [] and r["esd_ppg"] == 9.8
    case["frac_emw_ppg"] = 12.5
    r = evaluate(case)
    assert abs(r["frac_margin_ppg"] - (12.5 - r["ecd_ppg"])) < 1e-12 and r["warnings"] == []
    case["frac_emw_ppg"] = 10.3
    assert [w["code"] for w in evaluate(case)["warnings"]] == ["ecd_over_frac"]
    case["frac_emw_ppg"] = 10.7
    assert [w["code"] for w in evaluate(case)["warnings"]] == ["ecd_near_frac"]
    case["frac_emw_ppg"] = 9.5
    assert [w["code"] for w in evaluate(case)["warnings"]] == ["esd_over_frac"]
    case["frac_emw_ppg"] = 0
    with pytest.raises(InputError):
        evaluate(case)


def test_implausible_ecd_is_flagged():
    case = {
        "mud_weight_ppg": 16, "flow_rate_gpm": 900, "tvd_ft": 30000,
        "rheology": {"fann": {"600": 90, "300": 55, "100": 25, "3": 6}},
        "sections": [{"name": "tight", "hole_id_in": 6.276, "pipe_od_in": 5.0, "length_ft": 30000}],
    }
    assert [w["code"] for w in evaluate(case)["warnings"]] == ["ecd_implausible"]


def test_cli_frac_flag(capsys):
    from ecd_check.cli import main

    assert main(["--example", "--frac", "10.3"]) == 0
    out = capsys.readouterr().out
    assert "margin -0.215 ppg" in out and "CHECK: ECD 10.52 ppg exceeds the fracture gradient" in out
