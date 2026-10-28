# Contributing

Put independent utilities under `projects/<Name>/`. Each project should include a README, build instructions, license information and appropriate checks. Keep generated binaries and local settings out of Git; publish binaries as release assets.

Keep changes focused. Describe the problem, behavior changes and validation in pull requests. Run the checks for the affected project. Avoid telemetry and unnecessary background activity. Preserve attribution and third-party notices.

- DesktopKeys: run `./Build.ps1`, then `DesktopKeys.exe --verify <absolute-report-path>` with the normal instance stopped and modifier keys released.
- LiteNetMonitor: from its project folder run `python -m unittest discover -s tests -v`.

Use separate release versions for each utility. Existing LiteNetMonitor tags remain `vX.Y.Z`; DesktopKeys uses `desktopkeys-vX.Y.Z`.
