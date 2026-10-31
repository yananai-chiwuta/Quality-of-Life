# DesktopKeys

Map **PgUp → Win+Ctrl+Left** and **PgDn → Win+Ctrl+Right** to switch Windows virtual desktops. One switch per press; modified PgUp/PgDn shortcuts remain available. No tray icon or settings window.

**Menu/Application key → Alt+Tab** switches to the previous app window. This is the key near the right Ctrl/Windows keys, often marked with a menu or mouse symbol. Each press completes Alt+Tab, so repeated presses toggle between your two most recent windows. It switches windows rather than browser tabs. Its usual right-click menu is replaced while DesktopKeys runs; Shift+F10 remains available for a keyboard context menu.

## Use

Download DesktopKeys from the repository Releases page, extract to a permanent folder and double-click `DesktopKeys.exe`. Exit PowerToys Keyboard Manager first if it maps these same keys. The first normal launch enables startup at sign-in for your Windows account. Keep the executable in that location; launching from a new location updates its startup path.

You need at least two virtual desktops to switch between them. Win+Tab opens Task View. Startup means Windows sign-in, not a system service before login.

## Controls (PowerShell)

```powershell
./DesktopKeys.exe --stop
./DesktopKeys.exe --disable-startup
./DesktopKeys.exe --enable-startup
```

Stopping restores normal PgUp/PgDn and Menu-key behavior until the next launch. Disabling startup persists across manual launches. To uninstall, disable startup, stop the app, then delete its folder. Task Manager can also end DesktopKeys.

Startup uses `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, value `DesktopKeys`. The preference is saved at `HKCU\Software\QualityOfLife\DesktopKeys`, value `StartupDisabled`. No administrator access is required.

## Build and check

Windows 10/11 and .NET Framework 4.x are required. No NuGet packages or downloaded runtimes are used.

```powershell
./Build.ps1
./DesktopKeys.exe --verify "$PWD\verification.txt"
```

Stop the regular instance first. Verification checks real source-key injection, hotkey routing, native structure sizes, target key sequences and registration cleanup without switching desktops, switching apps or changing startup. Try the actual desktop switch in your session too.

The executable includes the original desktop-and-arrows icon in `DesktopKeys.ico`; its editable vector source is `DesktopKeys.svg`. It runs as a single background process and waits on Windows messages. Memory use varies by PC. Protected desktops and some elevated windows may block SendInput. Builds are unsigned.

## Implementation and license

`DesktopKeys.cs` contains all behavior. `Build.ps1` invokes the Windows .NET Framework C# compiler. No telemetry, network access, key logging or polling loop. [MIT license](LICENSE).

Windows API references: [RegisterHotKey](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey), [SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput).
