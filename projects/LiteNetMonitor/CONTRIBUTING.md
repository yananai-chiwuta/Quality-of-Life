# Contributing

Issues and pull requests are welcome. Keep the app focused, lightweight, and usable across Windows, macOS, and Linux. The interface uses the Python standard library's Tkinter; avoid adding another UI toolkit.

## Set up

Use Python 3.11 or newer, create a virtual environment, and install the runtime dependency:

```sh
python -m venv .venv
python -m pip install -r requirements.txt
```

If working on optional tray behavior on Windows or Linux, also install `requirements-tray.txt`. Linux may require a distribution package for Tkinter, commonly `python3-tk`.

Run the app with `python LiteNetMonitor.pyw`. Before opening a pull request, check that modified Python files compile and run the tests with `python -m unittest discover -s tests -v`. Desktop integration tests skip if no graphical display is available.

## Pull requests

Describe the user-visible change and the platforms you exercised. Keep changes narrow, preserve existing settings where possible, and include tests for core behavior when practical. Do not claim a platform was tested unless you ran it there.

By submitting a contribution, you agree that it is offered under the repository's MIT license.

## Versioned releases

Update `APP_VERSION` in `netmonitor_core.py`, add a dated changelog entry, refresh the README download links, and update `.github/RELEASE_NOTES.md`. Use `major.minor.patch`: fixes increment patch, compatible features increment minor, and breaking changes increment major.

To build locally, install `pyinstaller==6.22.2` and run `python tools/build_release.py`. Build on the target OS and architecture; archives are written to `dist/releases/`. Linux needs a graphical display (or `xvfb-run -a`), including for the packaged startup check.

Maintainers publish by pushing a matching `vX.Y.Z` tag. The build workflow checks the version, runs tests on all four targets, starts each packaged app, and publishes archives plus checksums only after every build succeeds. Running the workflow manually produces artifacts without creating a public release.
