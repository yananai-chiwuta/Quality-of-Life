# Repository layout and releases

`projects/DesktopKeys` contains a .NET Framework Windows hotkey utility. `projects/LiteNetMonitor` contains the Python/Tk network monitor, its tests and packaging script. GitHub Actions live at the repository root.

The LiteNetMonitor CI and build workflows run commands from its project directory. Its legacy `v*` tags remain supported; release assets remain available under the renamed repository. DesktopKeys has a separate Windows build/check workflow and release tag namespace.

DesktopKeys uses RegisterHotKey and SendInput, plus a hidden message-only window. It has no tray icon, timer, network access or keyboard logging. The user-scoped Run registry entry launches it at sign-in. Command-line switches manage startup and exit. See its README for configuration and limitations.

The migration moves source files in one commit while retaining the original Git history and release tags. GitHub repository rename preserves old URL redirects. No replacement repository is created at the old name.
