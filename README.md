# ECD Check

Annular pressure loss and equivalent circulating density (ECD) screening for drilling, using the API RP 13D (1995) power-law annulus model. A small, tested Python library and a free browser tool that runs entirely client side.

**Live tool:** https://wjwhitmire.github.io/ecd-check/

**This is a screening tool. It is not a replacement for a full hydraulics program.** It gives a fast, transparent first number for annular pressure loss and ECD. It does not model temperature and pressure effects on rheology, pipe rotation, eccentricity, tool joints, cuttings load, or surge and swab. Use a full hydraulics program for well design and for any decision near a fracture or pore pressure limit.

## What it computes

Inputs, in oilfield units:

- Mud weight (ppg)
- Rheology, either as Fann dial readings (600, 300, 200, 100, 6, 3 rpm; 600, 300, 100 and 3 are needed for the API annulus model) or as PV (cP) and YP (lbf/100 ft2)
- Flow rate (gpm)
- True vertical depth of the point of interest (ft)
- Annular sections: name, hole or casing ID (in), pipe OD (in), measured length (ft)

Outputs:

- Per section: annular velocity (ft/min), effective viscosity (cP), Reynolds number, flow regime, pressure loss (psi)
- Total annular pressure loss (APL), hydrostatic pressure at TVD, bottomhole circulating pressure (BHCP), ECD
- Optional fracture gradient at the TVD (ppg EMW, `frac_emw_ppg` in a case, `--frac` in the CLI): margin = frac gradient - ECD, shown as a readout and a line on the chart
- Plain warnings (`warnings` in the result): ECD above 25 ppg (heavier than any drilling fluid, so an input is wrong); annular friction adding more than 2 ppg to the mud weight (unusual for a drilling annulus); static mud weight (ESD) at or above the fracture gradient; ECD above it; ECD within 0.3 ppg of it. ESD here is the mud weight as entered, since temperature and pressure effects are not modeled
- A what-if sweep of ECD against flow rate, with the current rate marked and transitional-flow bands shaded

## Quick start

```bash
pip install -e .[dev]
pytest -q

ecd-check --example
ecd-check --example --sweep
ecd-check case.json --json
ecd-check --sections sections.csv --mw 9.8 --q 550 --tvd 9800 --fann 600=52,300=33,200=25,100=17,6=6,3=5
ecd-check --sections sections.csv --mw 9.8 --q 550 --tvd 9800 --pv 19 --yp 14
```

Python:

```python
from ecd_check import evaluate, ecd_sweep, EXAMPLE_CASE

res = evaluate(EXAMPLE_CASE)
print(res["ecd_ppg"], res["apl_psi"])
for s in res["sections"]:
    print(s["name"], s["va_fpm"], s["regime"], s["dp_psi"])
```

Case format (JSON):

```json
{
  "mud_weight_ppg": 9.8,
  "flow_rate_gpm": 550,
  "tvd_ft": 9800,
  "rheology": {"fann": {"600": 52, "300": 33, "200": 25, "100": 17, "6": 6, "3": 5}},
  "sections": [
    {"name": "Casing 8.835 in ID x 5 in DP", "hole_id_in": 8.835, "pipe_od_in": 5.0, "length_ft": 9200},
    {"name": "Open hole 8.5 in x 5 in DP (curve)", "hole_id_in": 8.5, "pipe_od_in": 5.0, "length_ft": 1400},
    {"name": "Open hole 8.5 in x 4.5 in DP (lateral)", "hole_id_in": 8.5, "pipe_od_in": 4.5, "length_ft": 8500},
    {"name": "Open hole 8.5 in x 6.75 in BHA", "hole_id_in": 8.5, "pipe_od_in": 6.75, "length_ft": 280}
  ]
}
```

PV/YP instead of dial readings: `"rheology": {"pv_cp": 19, "yp": 14}`.

Section CSV/TSV for the CLI and the browser tool: columns `name, hole_id_in, pipe_od_in, length_ft`. A header row is optional and detected automatically. Comma or tab separated. Blank lines and lines starting with `#` are skipped. Extra columns are ignored. Quoted fields containing the separator are not supported. The browser CSV export prefixes any cell that starts with =, +, -, @, tab or CR with a single quote so spreadsheets do not run it as a formula. The browser tool caps files at 5 MB and 50,000 rows and the model at 200 sections.

The built-in example is labeled "Example data". It is a Permian-style horizontal well: 9-5/8 in 40 lb/ft intermediate casing (8.835 in ID) over 5 in drill pipe, an 8-1/2 in curve and lateral with a tapered 5 in by 4-1/2 in string, and 6-3/4 in collars in the BHA, with a 9.8 ppg water-based mud. It is illustrative, not a real well.

## Method

Source: American Petroleum Institute, *API Recommended Practice 13D, Rheology and Hydraulics of Oil-well Drilling Fluids*, Third Edition, June 1995, power-law annulus pressure loss procedure. The equations below are the annulus equations of that edition in oilfield units. Later editions (2003 onward, and the 2006 and 2017 revisions) moved to the Herschel-Bulkley model with different regime criteria; this tool does not implement those.

Symbols: D2 hole or casing ID (in), D1 pipe OD (in), Q flow rate (gpm), MW mud weight (ppg), L section length (ft), R_x dial reading at x rpm (deg).

### Rheology

API annulus power-law parameters from the 100 and 3 rpm readings:

```
n_a = 0.657 log10(R100 / R3)
K_a = 5.11 R100 / 170.2^n_a                     dyne s^n / cm^2
```

0.657 = 1 / log10(100/3). 5.11 converts a dial reading to shear stress in dyne/cm2 (1 deg = 1.0678 lbf/100 ft2 = 5.11 dyne/cm2 on an R1-B1-F1 viscometer). 170.2 s^-1 is the shear rate at 100 rpm (1.7023 s^-1 per rpm).

If 100 rpm or 3 rpm is not available (always the case with PV/YP input), the annulus uses the 600/300 power law and the output says so:

```
n = 3.32 log10(R600 / R300)
K = 5.11 R300 / 511^n                           dyne s^n / cm^2
```

PV/YP conversion (Bingham): `R600 = 2 PV + YP`, `R300 = PV + YP`.

### Annulus, per section

```
Va     = 24.48 Q / (D2^2 - D1^2)                ft/min
         (API writes 0.408 Q / (D2^2 - D1^2) in ft/s; 0.408 x 60 = 24.48)
gamma  = 144 Va_fps / (D2 - D1)                 1/s
mu_ea  = 100 K_a gamma^(n_a - 1) ((2 n_a + 1) / (3 n_a))^n_a      cP
Re_a   = 928 (D2 - D1) Va_fps MW / mu_ea
```

Regime and Fanning friction factor:

```
Re_c1 = 3470 - 1370 n_a      Re_c2 = 4270 - 1370 n_a
laminar       Re_a <  Re_c1      f = 24 / Re_a
turbulent     Re_a >  Re_c2      f = a / Re_a^b
                                  a = (log10 n_a + 3.93) / 50
                                  b = (1.75 - log10 n_a) / 7
transitional  Re_c1 <= Re_a <= Re_c2
              f = (Re_a - Re_c1) / 800 x (f_turb(Re_c2) - f_lam(Re_c1)) + f_lam(Re_c1)
```

The transitional factor is a straight line in Re between the laminar value at Re_c1 and the turbulent value at Re_c2 (Re_c2 - Re_c1 = 800). It is continuous at both ends.

Pressure loss:

```
dP = f Va_fps^2 MW / (25.81 (D2 - D1)) x L      psi
```

### Totals

```
APL   = sum of dP over all sections             psi
P_hyd = 0.052 MW TVD                            psi
BHCP  = P_hyd + APL                             psi
ECD   = MW + APL / (0.052 TVD)                  ppg
```

At Q = 0 every section reports "no flow", APL = 0, and ECD = MW exactly.

### Unit checks

Each constant is checked against SI conversions in `tests/test_core.py::test_unit_constants_derived_from_si`.

- **Annular velocity, 24.48.** Q gpm x 0.133681 ft3/gal = ft3/min. Area = (pi/4)(D2^2 - D1^2)/144 ft2. Va = Q x 0.133681 x 144 x 4/pi / (D2^2 - D1^2) = 24.51 Q / (D2^2 - D1^2) ft/min. API rounds to 0.408 ft/s (24.48 ft/min); this tool uses the API value, a 0.12 percent difference.
- **Shear rate, 144.** The annulus is treated as a slot of width h = (D2 - D1)/2 in. The Newtonian slot wall shear rate is 6 V/h. With V in ft/s and h in ft: 6 V x 24 / (D2 - D1) = 144 V / (D2 - D1) s^-1.
- **Effective viscosity, 100.** K in dyne s^n/cm2 times gamma^(n-1) gives poise; x 100 gives cP. ((2n+1)/(3n))^n is the slot Rabinowitsch-Mooney correction for a power-law fluid.
- **Reynolds, 928.** Re = rho V Dh / mu, Dh = D2 - D1. 1 ppg = 119.83 kg/m3, 1 in = 0.0254 m, 1 ft/s = 0.3048 m/s, 1 cP = 0.001 Pa s. 119.83 x 0.0254 x 0.3048 / 0.001 = 927.7, rounded to 928.
- **Pressure loss, 25.81.** Fanning: dP/L = 2 f rho V^2 / Dh. With rho in ppg, V in ft/s, Dh in in, and the result in psi/ft: 2 x 119.83 x 0.3048^2 / 0.0254 Pa/m per (ppg ft2/s2 / in) = 876.6 Pa/m = 0.03875 psi/ft, and 1/0.03875 = 25.81.
- **Hydrostatic, 0.052.** 1 ppg = 7.4805 gal/ft3 x 1 lb/gal / 144 in2/ft2 = 0.05195 psi/ft, rounded to 0.052.
- **ECD.** APL / (0.052 TVD) has units psi / (psi/ft/ppg x ft) = ppg.

### Note on K_a

- Some summaries of RP 13D write `K_a = 5.11 R100 / 511^n_a`. The 1995 annulus equation divides by 170.2^n_a, the shear rate of the 100 rpm reading. Dividing a 100 rpm stress by 511^n would evaluate K at the wrong shear rate. This tool uses 170.2. K_a is in dyne s^n/cm2, not a cP-like unit; the factor 100 in mu_ea converts poise to cP.
- Va is in ft/s inside gamma, Re and dP, and in ft/min for display.

## Limits

- **Screening only.** Not a replacement for a full hydraulics program.
- **Isothermal and incompressible.** Rheology is taken at the measured (surface) condition. Downhole temperature thins water-based mud and changes oil-based mud strongly; pressure thickens oil-based mud. Neither is modeled.
- **Concentric annulus, no rotation, no tool joints.** Eccentric pipe in a lateral usually lowers laminar annular loss relative to concentric. Rotation and tool joints usually raise it. Neither is modeled.
- **Clean mud, steady state.** No cuttings load, no gel breaking, no surge or swab, no transient pump-up.
- **APL is applied at the TVD you give.** List only the annular sections from surface down to the point of interest. All loss in the listed sections is added at that TVD.
- **Power law has no yield stress.** With PV/YP only (600/300 fallback), low-shear behavior is not represented, and annular loss in large, slow annuli is usually under-predicted. Give 100 and 3 rpm readings when you have them.
- **Transitional flow is uncertain.** The 1995 transition is a linear blend. Across the band, computed loss can fall while rate rises, so the ECD-vs-rate curve can dip. The browser chart shades rates where any section is transitional, the result notes name the sections, and a warning under the chart (and `ecd-check --sweep`) states each rate range where computed ECD falls as rate rises. That fall is a model artifact, not a real ECD reduction; do not raise rate to lower ECD on the strength of it. `sweep_dips()` returns those ranges.
- **Range guards.** Rejects pipe OD >= hole ID, negative values, zero or negative mud weight, TVD or PV, mud weight above 25 ppg, hole ID above 60 in, n above 2, and dial readings that increase as speed drops. n above 1 is allowed with a warning.
- **Not the current API model.** Results will differ from API RP 13D 2006/2017 (Herschel-Bulkley) and from commercial programs.

## Validation

- `tests/test_core.py`: hand-computed laminar case (8.5 in x 5 in, 300 gpm, 10 ppg; dP = 19.870 psi per 1000 ft) and turbulent case (6.276 in x 5 in, 500 gpm, 12 ppg; dP = 276.97 psi per 1000 ft), each with every intermediate value written out in comments; transition continuity; ECD = MW at zero flow; monotonic ECD in Q in laminar-only and turbulent-only bands and on the example outside transition; PV/YP conversion and fallback note; unit-constant derivations; bad input (pipe OD >= hole ID, negative values, NaN, non-monotonic dials, missing rheology); CSV parsing; CLI.
- `tests/vectors.json` (generated by `tests/make_vectors.py`) holds reference cases and parse cases. `web/parity.test.mjs` runs the JavaScript core from `web/app.html` against them with a relative tolerance of 1e-9, including error messages.

```bash
python tests/make_vectors.py && node web/parity.test.mjs
python web/build_pages.py        # writes docs/index.html
```

## Repository layout

```
src/ecd_check/core.py     model
src/ecd_check/parse.py    section table parser
src/ecd_check/cli.py      command line
tests/                    pytest suite, vectors and generator
web/app.html              browser tool (core in <script id="core">)
web/parity.test.mjs       JS/Python parity check
web/build_pages.py        builds docs/index.html for GitHub Pages
```

## License

MIT. Copyright (c) 2026 Will Whitmire. See `LICENSE`.
