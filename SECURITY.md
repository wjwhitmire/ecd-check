# Security

## Data handling

- The browser tool (`web/app.html`, published as `docs/index.html`) makes no network calls. No fetch, XHR, WebSocket, beacons or analytics. The only external resource is the Google Fonts stylesheet.
- No data leaves the browser. Inputs and loaded files are processed in memory and are not stored. Files are read with `<input type=file>` and `FileReader`, capped at 5 MB and 50,000 rows.
- User-supplied text is rendered with `textContent`, never `innerHTML`. There is no `eval`, no `new Function`, and no inline event-handler attributes.
- The Python library has no runtime dependencies, makes no network calls, uses no `pickle`, `eval` or shell calls, and reads only the file paths given on the command line.

## Reporting a vulnerability

Open a private security advisory on this repository (Security tab, "Report a vulnerability"). Include steps to reproduce and the affected file. Please do not open a public issue for a security problem.
