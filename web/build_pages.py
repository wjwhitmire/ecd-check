"""Wrap web/app.html into docs/index.html as a full HTML document for GitHub Pages.

Run: python web/build_pages.py
"""

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def build() -> str:
    with open(os.path.join(HERE, "app.html"), encoding="utf-8") as fh:
        src = fh.read()
    m = re.search(r"<style>.*?</style>", src, flags=re.S)
    if not m:
        raise SystemExit("app.html: <style> block not found")
    head = src[: m.end()]
    body = src[m.end():].lstrip("\n")
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        '<meta name="description" content="ECD Check: annular pressure loss and ECD screening, API RP 13D (1995) power-law annulus model. Runs in your browser.">\n'
        f"{head}\n</head>\n<body>\n{body}</body>\n</html>\n"
    )


def main() -> None:
    out_dir = os.path.join(ROOT, "docs")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "index.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(build())
    print("wrote docs/index.html")


if __name__ == "__main__":
    main()
