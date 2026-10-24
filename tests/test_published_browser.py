"""Browser test of the page exactly as GitHub Pages serves it.

docs/ is copied to a temporary folder, the publish placeholders are filled
the way the release script fills them, and the copy is served under
/ecd-check/ on localhost. Headless Chromium then runs the main workflows and
fails on any page error, console error or Content-Security-Policy violation.

Needs the playwright package and its Chromium; skipped when they are missing.
"""

import functools
import http.server
import shutil
import threading
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
NAME = "ecd-check"
FILL = {
    "https://wjwhitmire.github.io/ecd-check/": f"https://wjwhitmire.github.io/{NAME}/",
    "wjwhitmire": "wjwhitmire",
    "https://github.com/wjwhitmire/ecd-check": f"https://github.com/wjwhitmire/{NAME}",
}
WATCH = """
window.__csp = [];
document.addEventListener('securitypolicyviolation', e => window.__csp.push(e.violatedDirective + ' ' + e.blockedURI));
"""


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("pages")
    dest = root / NAME
    shutil.copytree(ROOT / "docs", dest)
    for f in dest.rglob("*"):
        if f.suffix in (".html", ".js", ".json", ".webmanifest", ".css", ".txt", ".xml"):
            text = f.read_text(encoding="utf-8")
            for k, v in FILL.items():
                text = text.replace(k, v)
            f.write_text(text, encoding="utf-8")
    handler = functools.partial(QuietHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/{NAME}/"
    server.shutdown()


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # browser binary not installed
            pytest.skip(f"Chromium not available: {exc}")
        yield b
        b.close()


def open_page(browser, url, width=1280, **ctx):
    context = browser.new_context(viewport={"width": width, "height": 900}, **ctx)
    context.route("https://fonts.googleapis.com/**", lambda r: r.abort())
    context.route("https://fonts.gstatic.com/**", lambda r: r.abort())
    context.add_init_script(WATCH)
    page = context.new_page()
    page.problems = []
    page.on("pageerror", lambda e: page.problems.append(f"pageerror: {e}"))
    page.on(
        "console",
        lambda m: page.problems.append(f"console: {m.text}")
        if m.type == "error" and "fonts.g" not in m.text and "ERR_FAILED" not in m.text
        and not (m.location or {}).get("url", "").endswith("/favicon.ico")
        else None,
    )
    page.goto(url)
    return page


def assert_clean(page):
    csp = page.evaluate("window.__csp")
    assert not csp, csp
    assert not page.problems, page.problems
    assert page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 0
    for placeholder in FILL:
        assert placeholder not in page.content()


def ecd(page):
    return page.text_content("#o-ecd")


def edit(page, box, value):
    page.fill(f"#{box}", value)
    page.wait_for_timeout(50)


def test_example_on_load(site, browser):
    page = open_page(browser, site)
    assert ecd(page) == "10.52"
    assert page.text_content("#o-apl") == "365"
    assert page.locator("#res-body tr").count() == 4
    assert page.locator("#chart path.series").count() == 1
    assert_clean(page)


def test_zero_flow_gives_mud_weight(site, browser):
    page = open_page(browser, site)
    edit(page, "q", "0")
    assert ecd(page) == "9.80"


def test_pv_yp_mode(site, browser):
    page = open_page(browser, site)
    page.click("label[for=rh-pvyp]")
    assert "PV/YP converted" in page.text_content("#notes")
    assert "600/300 rpm fallback" in page.text_content("#rheo-line")


def test_error_disables_copy_and_hides_results(site, browser):
    page = open_page(browser, site)
    edit(page, "mw", "0")
    assert "Mud weight must be greater than 0" in page.text_content("#status")
    assert page.is_hidden("#results")
    assert page.is_disabled("#copy-csv")
    edit(page, "mw", "9.8")
    assert page.is_enabled("#copy-csv")


def test_load_sections_file_and_copy(site, browser, tmp_path):
    f = tmp_path / "s.csv"
    f.write_text("name,hole_id_in,pipe_od_in,length_ft\nCsg,8.835,5,9200\nOH,8.5,5,10180\n")
    page = open_page(browser, site)
    page.set_input_files("#sec-file", str(f))
    page.wait_for_function("document.querySelectorAll('#res-body tr').length === 2")
    page.evaluate("Object.defineProperty(navigator, 'clipboard', {value: undefined})")
    page.click("#copy-csv")
    assert "ecd" in page.input_value("#csv-text").lower()


def test_bad_first_row_message(site, browser, tmp_path):
    f = tmp_path / "s.csv"
    f.write_text("Csg,8.835,abc,9200\n")
    page = open_page(browser, site)
    page.set_input_files("#sec-file", str(f))
    page.wait_for_function("document.getElementById('status').textContent.includes('Line 1')")
    assert "neither a header row" in page.text_content("#status")


def test_phone_width(site, browser):
    page = open_page(browser, site, width=400, has_touch=True, is_mobile=True)
    assert ecd(page) == "10.52"
    assert_clean(page)


def test_frac_gradient_margin_and_warning(site, browser):
    page = open_page(browser, site)
    assert page.text_content("#o-margin") == "n/a"
    edit(page, "frac", "12.5")
    assert page.text_content("#o-margin") == "1.98"
    assert page.locator("#chart line.frac-line").count() == 1
    edit(page, "frac", "10.3")
    assert page.text_content("#o-margin") == "-0.22"
    assert "exceeds the fracture gradient" in page.text_content("#density-warn")
    page.click("#load-example")
    assert page.input_value("#frac") == ""
    assert page.text_content("#density-warn") == ""
