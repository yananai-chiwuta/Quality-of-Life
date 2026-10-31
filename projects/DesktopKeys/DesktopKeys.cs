// DesktopKeys: desktop switching and Menu-key Alt+Tab, using Windows and .NET Framework only.
// Build: see Build.ps1. No tray icon; startup is enabled on first launch. No keyboard logging, network access or administrator rights.
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class DesktopKeys
{
    internal const string WindowTitle = "DesktopKeys.22c91055.Controller";
    internal const int StopMessage = 0x8001;
    internal static readonly UIntPtr InputMarker = new UIntPtr(0x44534B59u);

    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "--stop")
        {
            IntPtr window = FindWindowEx(new IntPtr(-3), IntPtr.Zero, null, WindowTitle);
            if (window != IntPtr.Zero) PostMessage(window, StopMessage, IntPtr.Zero, IntPtr.Zero);
            return 0;
        }
        if (args.Length == 1 && (args[0] == "--disable-startup" || args[0] == "--enable-startup"))
        {
            SetStartup(args[0] == "--enable-startup");
            return 0;
        }
        bool verify = args.Length == 2 && args[0] == "--verify";
        bool created;
        using (var mutex = new Mutex(true, "Local\\DesktopKeys.22c91055", out created))
        {
            if (!created)
            {
                if (verify) File.WriteAllText(args[1], "FAIL: DesktopKeys is already running.");
                else MessageBox.Show("DesktopKeys is already running. Use DesktopKeys.exe --stop to exit.", "DesktopKeys");
                return 1;
            }
            try
            {
                if (verify) { Verify(args[1]); return 0; }
                Application.EnableVisualStyles();
                using (var context = new HeadlessContext()) Application.Run(context);
                return 0;
            }
            catch (Exception error)
            {
                if (verify) File.WriteAllText(args[1], "FAIL: " + error);
                else MessageBox.Show(error.Message, "DesktopKeys", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
        }
    }

    internal sealed class HotkeyWindow : NativeWindow, IDisposable
    {
        private readonly Action<ushort> onHotkey;
        private readonly Action onStop;
        private readonly KeyboardHook menuCallback;
        private IntPtr menuHook;
        private bool menuDown;
        private const int MenuSwitchMessage = 0x8002;
        internal bool Enabled { get; private set; }

        internal HotkeyWindow(Action<ushort> callback, Action stop)
        {
            onHotkey = callback; onStop = stop;
            menuCallback = FilterMenuKey;
            CreateHandle(new CreateParams { Caption = WindowTitle, Parent = new IntPtr(-3) });
        }

        internal void Enable()
        {
            if (Enabled) return;
            uint[] keys = { 0x21, 0x22 };
            for (int index = 0; index < keys.Length; index++)
            {
                if (RegisterHotKey(Handle, index + 1, 0x4000, keys[index])) continue;
                int error = Marshal.GetLastWin32Error();
                for (int registered = 1; registered <= index; registered++) UnregisterHotKey(Handle, registered);
                throw new Win32Exception(error,
                    "Could not reserve PgUp and PgDn. Exit another key mapper and try again.");
            }
            menuHook = SetWindowsHookEx(13, menuCallback, GetModuleHandle(null), 0);
            if (menuHook == IntPtr.Zero)
            {
                int error = Marshal.GetLastWin32Error();
                UnregisterHotKey(Handle, 1); UnregisterHotKey(Handle, 2);
                throw new Win32Exception(error, "Could not intercept the Menu key.");
            }
            Enabled = true;
        }

        internal void Disable()
        {
            if (!Enabled) return;
            Enabled = false;
            UnregisterHotKey(Handle, 1); UnregisterHotKey(Handle, 2);
            UnhookWindowsHookEx(menuHook); menuHook = IntPtr.Zero; menuDown = false;
        }

        private IntPtr FilterMenuKey(int code, IntPtr message, IntPtr data)
        {
            // Consume BOTH edges: letting the original key-up through can open a
            // context menu in the window we just switched to. Ignore auto-repeat.
            if (code >= 0 && Enabled && Marshal.ReadInt32(data) == (int)Keys.Apps)
            {
                int kind = message.ToInt32();
                if (kind == 0x0100 || kind == 0x0104) menuDown = true;
                if (kind == 0x0101 || kind == 0x0105)
                {
                    if (menuDown) PostMessage(Handle, MenuSwitchMessage, IntPtr.Zero, IntPtr.Zero);
                    menuDown = false;
                }
                return new IntPtr(1);
            }
            return CallNextHookEx(menuHook, code, message, data);
        }

        protected override void WndProc(ref Message message)
        {
            if (message.Msg == 0x0312 && Enabled)
            {
                if (message.WParam.ToInt32() == 1) onHotkey(0x25);
                if (message.WParam.ToInt32() == 2) onHotkey(0x27);
                return;
            }
            if (message.Msg == MenuSwitchMessage)
            {
                if (Enabled) onHotkey(0x09);
                return;
            }
            if (message.Msg == StopMessage) { onStop(); return; }
            base.WndProc(ref message);
        }

        public void Dispose() { Disable(); DestroyHandle(); }
    }

    private const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
    private const string PreferencesKey = @"Software\QualityOfLife\DesktopKeys";
    private static void SetStartup(bool enabled)
    {
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(RunKey))
        {
            if (enabled) key.SetValue("DesktopKeys", "\"" + Application.ExecutablePath + "\"", RegistryValueKind.String);
            else key.DeleteValue("DesktopKeys", false);
        }
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(PreferencesKey))
            key.SetValue("StartupDisabled", enabled ? 0 : 1, RegistryValueKind.DWord);
    }
    private sealed class HeadlessContext : ApplicationContext
    {
        private readonly HotkeyWindow window;
        internal HeadlessContext()
        {
            window = new HotkeyWindow(SendShortcut, ExitThread);
            try
            {
                window.Enable();
                using (RegistryKey key = Registry.CurrentUser.OpenSubKey(PreferencesKey))
                    if (key == null || Convert.ToInt32(key.GetValue("StartupDisabled", 0)) == 0) SetStartup(true);
            }
            catch { window.Dispose(); throw; }
        }
        protected override void ExitThreadCore() { window.Disable(); base.ExitThreadCore(); }
        protected override void Dispose(bool disposing)
        {
            if (disposing) window.Dispose();
            base.Dispose(disposing);
        }
    }

    // INPUT contains the full union so its native size is 40 bytes on x64, 28 on x86.
    [StructLayout(LayoutKind.Sequential)] internal struct Input { internal uint Type; internal InputUnion Data; }
    [StructLayout(LayoutKind.Explicit)] internal struct InputUnion
    {
        [FieldOffset(0)] internal KeyboardInput Keyboard;
        [FieldOffset(0)] internal MouseInput Mouse;
    }
    [StructLayout(LayoutKind.Sequential)] internal struct KeyboardInput
    {
        internal ushort Key, Scan;
        internal uint Flags, Time;
        internal UIntPtr Extra;
    }
    [StructLayout(LayoutKind.Sequential)] internal struct MouseInput
    {
        internal int X, Y;
        internal uint MouseData, Flags, Time;
        internal UIntPtr Extra;
    }
    internal static Input Key(ushort key, bool up)
    {
        bool extended = key == 0x25 || key == 0x27 || key == 0x5B || key == 0x21 || key == 0x22 || key == (ushort)Keys.Apps;
        return new Input { Type = 1, Data = new InputUnion { Keyboard = new KeyboardInput {
            Key = key, Flags = (up ? 2u : 0u) | (extended ? 1u : 0u), Extra = InputMarker } } };
    }
    internal static Input[] BuildShortcut(ushort arrow)
    {
        if (arrow == 0x09)
        {
            bool altHeld = Held(0xA4) || Held(0xA5);
            var switchEvents = new List<Input>();
            if (!altHeld) switchEvents.Add(Key(0xA4, false));
            switchEvents.Add(Key(0x09, false)); switchEvents.Add(Key(0x09, true));
            if (!altHeld) switchEvents.Add(Key(0xA4, true));
            return switchEvents.ToArray();
        }
        // Preserve modifiers physically held after the original hotkey was queued.
        var events = new List<Input>();
        bool winHeld = Held(0x5B) || Held(0x5C);
        bool ctrlHeld = Held(0xA2) || Held(0xA3);
        if (!winHeld) events.Add(Key(0x5B, false));
        if (!ctrlHeld) events.Add(Key(0xA2, false));
        events.Add(Key(arrow, false)); events.Add(Key(arrow, true));
        if (!ctrlHeld) events.Add(Key(0xA2, true));
        if (!winHeld) events.Add(Key(0x5B, true));
        return events.ToArray();
    }
    private static bool Held(int key) { return (GetAsyncKeyState(key) & 0x8000) != 0; }
    internal static void SendShortcut(ushort arrow)
    {
        Input[] events = BuildShortcut(arrow);
        uint sent = SendInput((uint)events.Length, events, Marshal.SizeOf(typeof(Input)));
        if (sent != events.Length)
        {
            // Release only modifiers this batch pressed if injection was interrupted.
            var releases = new List<Input>();
            for (int index = 0; index < sent; index++)
            {
                ushort key = events[index].Data.Keyboard.Key;
                if ((events[index].Data.Keyboard.Flags & 2) == 0) releases.Add(Key(key, true));
            }
            if (releases.Count > 0) SendInput((uint)releases.Count, releases.ToArray(), Marshal.SizeOf(typeof(Input)));
        }
    }

    // Integration check: inject source keys into Windows, receive real WM_HOTKEY,
    // inspect the generated target sequence, but never inject a desktop switch.
    private static void Verify(string report)
    {
        if (Marshal.SizeOf(typeof(Input)) != (IntPtr.Size == 8 ? 40 : 28)) throw new Exception("INPUT layout is incorrect.");
        foreach (int key in new int[] { 0x10, 0x11, 0x12, 0x5B, 0x5C })
            if (Held(key)) throw new Exception("Release modifier keys before running verification.");
        var received = new List<ushort>();
        using (var window = new HotkeyWindow(delegate(ushort arrow) { received.Add(arrow); }, delegate { }))
        {
            window.Enable();
            InjectPage(0x21); PumpUntil(received, 1);
            InjectPage(0x22); PumpUntil(received, 2);
            VerifyMenuSuppression(received);
            if (received[0] != 0x25 || received[1] != 0x27 || received[2] != 0x09) throw new Exception("Incorrect hotkey dispatch.");
            foreach (ushort arrow in received)
            {
                Input[] events = BuildShortcut(arrow);
                ushort[] expectedKeys = arrow == 0x09 ? new ushort[] { 0xA4, 0x09, 0x09, 0xA4 } : new ushort[] { 0x5B, 0xA2, arrow, arrow, 0xA2, 0x5B };
                if (events.Length != expectedKeys.Length) throw new Exception("Incorrect shortcut length.");
                for (int index = 0; index < events.Length; index++)
                    if (events[index].Type != 1 || events[index].Data.Keyboard.Key != expectedKeys[index] ||
                        ((events[index].Data.Keyboard.Flags & 2) != 0) != (index >= events.Length / 2))
                        throw new Exception("Incorrect key sequence.");
            }
            window.Disable(); window.Enable(); window.Disable();
        }
        // Confirm exit/pause released all hotkeys by reserving them again.
        using (var window = new HotkeyWindow(delegate(ushort arrow) { }, delegate { })) window.Enable();
        File.WriteAllText(report, "PASS: native INPUT layout; real PgUp/PgDn/Menu routing; Menu down/up and repeats suppressed before reaching a focused window; no context menu; one switch per press; Win+Ctrl+Left/Right and Alt+Tab sequences; pause/resume; cleanup. No desktop-switch or app-switch shortcut was emitted.");
    }

    private sealed class MenuProbe : Form
    {
        internal int MenuMessages, ContextMenus;
        protected override void WndProc(ref Message message)
        {
            if ((message.Msg == 0x0100 || message.Msg == 0x0101 || message.Msg == 0x0104 || message.Msg == 0x0105)
                && message.WParam.ToInt32() == (int)Keys.Apps) MenuMessages++;
            if (message.Msg == 0x007B) ContextMenus++;
            base.WndProc(ref message);
        }
    }
    private static void VerifyMenuSuppression(List<ushort> received)
    {
        using (var probe = new MenuProbe { Text = "DesktopKeys Menu-key verification", Width = 340, Height = 100 })
        {
            probe.Show(); probe.Activate();
            var timeout = Stopwatch.StartNew();
            while (GetForegroundWindow() != probe.Handle && timeout.ElapsedMilliseconds < 2000)
            { Application.DoEvents(); Thread.Sleep(10); }
            if (GetForegroundWindow() != probe.Handle) throw new Exception("Could not focus the Menu-key test window.");
            Input[] held = { Key((ushort)Keys.Apps, false), Key((ushort)Keys.Apps, false) };
            if (SendInput(2, held, Marshal.SizeOf(typeof(Input))) != 2) throw new Exception("Menu press injection failed.");
            PumpFor(100);
            if (received.Count != 2) throw new Exception("Menu switched before release, or repeated while held.");
            Input[] release = { Key((ushort)Keys.Apps, true) };
            if (SendInput(1, release, Marshal.SizeOf(typeof(Input))) != 1) throw new Exception("Menu release injection failed.");
            PumpUntil(received, 3); PumpFor(100);
            if (received.Count != 3 || probe.MenuMessages != 0 || probe.ContextMenus != 0)
                throw new Exception("Menu key leaked to the foreground window or produced multiple switches.");
        }
    }
    private static void PumpFor(int milliseconds)
    {
        var timeout = Stopwatch.StartNew();
        while (timeout.ElapsedMilliseconds < milliseconds) { Application.DoEvents(); Thread.Sleep(10); }
    }
    private static void InjectPage(ushort key)
    {
        var events = new Input[] { Key(key, false), Key(key, true) };
        if (SendInput(2, events, Marshal.SizeOf(typeof(Input))) != 2) throw new Win32Exception("Source-key injection failed.");
    }
    private static void PumpUntil(List<ushort> received, int count)
    {
        var timeout = Stopwatch.StartNew();
        while (received.Count < count && timeout.ElapsedMilliseconds < 2000) { Application.DoEvents(); Thread.Sleep(10); }
        if (received.Count != count) throw new Exception("Hotkey was not delivered, or delivered more than once.");
    }
    [DllImport("user32.dll", SetLastError = true)] private static extern bool RegisterHotKey(IntPtr window, int id, uint modifiers, uint key);
    [DllImport("user32.dll")] private static extern bool UnregisterHotKey(IntPtr window, int id);
    [DllImport("user32.dll", SetLastError = true)] private static extern uint SendInput(uint count, Input[] events, int size);
    [DllImport("user32.dll")] private static extern short GetAsyncKeyState(int key);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after, string className, string windowName);
    [DllImport("user32.dll")] private static extern bool PostMessage(IntPtr window, int message, IntPtr wParam, IntPtr lParam);
    private delegate IntPtr KeyboardHook(int code, IntPtr message, IntPtr data);
    [DllImport("user32.dll", SetLastError = true)] private static extern IntPtr SetWindowsHookEx(int kind, KeyboardHook callback, IntPtr module, uint thread);
    [DllImport("user32.dll")] private static extern bool UnhookWindowsHookEx(IntPtr hook);
    [DllImport("user32.dll")] private static extern IntPtr CallNextHookEx(IntPtr hook, int code, IntPtr message, IntPtr data);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] private static extern IntPtr GetModuleHandle(string name);
    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
}
