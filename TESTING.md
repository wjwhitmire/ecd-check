# Testing

Every function of ECD Check, how it was tested and the result. Browser checks ran against the published form of the page: `git archive HEAD`, publish placeholders filled, `docs/` served under `/ecd-check/` on localhost, headless Chromium at 1280 px and 400 px (touch), light and dark.

## How to rerun

```bash
pip install -e .[dev]
pytest -q                                   # model, parser, CLI
python tests/make_vectors.py && node web/parity.test.mjs   # JS core matches Python
python web/build_pages.py                   # rebuild docs/index.html
pip install playwright && python -m playwright install chromium
pytest -q tests/test_published_browser.py   # published page under /ecd-check/, main workflows
```

`tests/test_published_browser.py` copies `docs/`, fills the publish placeholders, serves the copy under `/ecd-check/` and fails on page errors, console errors, CSP violations, sideways scroll or leftover placeholders. It skips itself without Playwright; CI runs it in the `browser` job.

Suite size: 45 pytest + 1,064 parity checks before this pass; 57 pytest (8 browser) + 1,512 parity checks after.

## Function inventory

### Browser page

| Function | What was done | Result |
|---|---|---|
| Page load, published form | Opened `/ecd-check/` | Pass: ECD 10.52 ppg, no errors or CSP violations |
| Layout 1280 / 400 px, light and dark | Scroll width | Pass |
| Touch targets | 400 px touch | Pass |
| Mud weight, flow rate, TVD | 0, 26, blank, -5, 1e999 | Pass: refused with a message, results hidden |
| Zero flow | Q = 0 | Pass: ECD = MW, sections show "no flow" |
| Fann readings | 600 below 300, 3 rpm 0, 100 rpm blank (fallback note), 200 and 6 blank | Pass |
| Rheology mode Fann / PV-YP | Click and arrow keys; PV 0, YP -1 | Pass |
| Data tag | "Example data" until an edit, then "Your data" | Pass |
| Annular sections table | Add (default row), pipe OD above hole ID, remove | Pass |
| Reset to example | Click | Pass |
| Load sections CSV/TSV | Header, no header, 3 columns, header in another order | Pass |
| Load: bad header, empty, header only, decimal-comma row, 201 sections, over 5 MB | | Pass: refused with a message |
| Load: data row with a bad number in line 1 | | Fail before (said "Could not read the header row"); pass after fix (names the line and says it is neither header nor data) |
| Summary chips and gauge | Read | Pass: APL 365, hydrostatic 4,994, BHCP 5,359 psi |
| Section results table, rheology line, notes | Read | Pass |
| What-if chart | Series, current rate, transitional bands, sweep range, hover tooltip, leave | Pass |
| Dip warning | Example has one dip (639 to 722 gpm) | Pass |
| Copy results as CSV | Clipboard | Pass |
| Copy with invalid inputs | Click | Fail before (button did nothing, no message); pass after fix (disabled until inputs are valid) |
| Copy fallback | No clipboard | Pass |
| Method and limits | Expand | Pass |
| Network | `fetch` from the page | Pass: blocked by CSP; no network features |
| Print | Print to PDF | Pass |
| `web/app.html` via file:// | Opened directly | Pass |

### CLI

| Command | Result |
|---|---|
| `--example`, `--sweep`, `--json` | Pass |
| `case.json`, `--q` override | Pass |
| `--sections file --mw --q --tvd --fann` and `--pv --yp` | Pass |
| No input, missing file, incomplete `--fann`, malformed `--fann`, `--mw nan`, JSON that is not an object | Pass: message and exit 2 |

### Library

`dial_from_pv_yp`, `rheology_params`, `friction_factor`, `section_hydraulics`, `normalize_case`, `evaluate`, `default_sweep_rates`, `ecd_sweep`, `sweep_dips`, `parse_sections_text`, `EXAMPLE_CASE`: covered by pytest and parity vectors. Pass.

## Correctness checks

The API RP 13D (1995) annulus equations were implemented again outside the repo from the published form (n_a = 0.657 log(R100/R3), K_a = 5.11 R100/170.2^n_a, Va = 0.408 Q/(D2^2 - D1^2), mu_ea = 100 K (144 Va/(D2 - D1))^(n-1) ((2n+1)/3n)^n, Re = 928 (D2 - D1) Va MW/mu_ea, laminar below 3470 - 1370 n, turbulent above 4270 - 1370 n, f = 24/Re, a/Re^b, linear transition, dP = f Va^2 MW/(25.81 (D2 - D1)) L). The critical Reynolds numbers, friction factors and transition blend were also checked against a published hydraulics reference. Both cores in the published page agree with it to every printed digit.

| Case | Hand calculation | Result |
|---|---|---|
| Example well, 550 gpm | APL 364.6184 psi, ECD 10.51550 ppg, three laminar sections and turbulent BHA | Pass |
| Zero flow | ECD = MW | Pass |
| 600/300 fallback with a transitional section | APL 681.6653, ECD 13.09241 | Pass |
| 30,000 ft, 900 gpm, tight annulus, turbulent | APL 28,944.99 psi | Pass |
| Open hole with no pipe (D1 = 0) | APL 7.3613 psi | Pass |
| Friction factor continuity at both critical Reynolds numbers | Equal to 1e-13 | Pass |
| Invalid: MW 0 or 26, negative rate, TVD 0, pipe OD equal to hole ID, increasing dial readings, PV 0, no sections, decimal comma | Refused | Pass |

## Automation audit

| Decision point | Before | After |
|---|---|---|
| Annular n and K basis | Already automatic: 100/3 rpm when present, else 600/300 with a note | No change |
| Section file columns | Already detected from the header, or by position | No change |
| Copy results | Dead button while inputs were invalid | Disabled until the inputs compute |
| First-row parse message | Blamed the header | Names the line and what it expected |
| TVD of the point of interest | Required | No change: only the user knows it (sections are MD) |
| Fracture gradient | Not an input | Optional box (and `--frac`): margin readout, a line on the chart, and a warning when ECD or ESD reaches it |
| Implausible ECD | Reported silently | Plain warning above 25 ppg ECD or more than 2 ppg of annular friction |

## Known limits

- Oilfield units only. Screening model only (see README).
