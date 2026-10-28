// DesktopKeys: two fixed global hotkeys, using Windows and .NET Framework only.
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
        internal bool Enabled { get; private set; }

        internal HotkeyWindow(Action<ushort> callback, Action stop)
        {
            onHotkey = callback; onStop = stop;
            CreateHandle(new CreateParams { Caption = WindowTitle, Parent = new IntPtr(-3) });
        }

        internal void Enable()
        {
            if (Enabled) return;
            bool up = RegisterHotKey(Handle, 1, 0x4000, 0x21);
            int upError = Marshal.GetLastWin32Error();
            bool down = RegisterHotKey(Handle, 2, 0x4000, 0x22);
            int downError = Marshal.GetLastWin32Error();
            if (!up || !down)
            {
                if (up) UnregisterHotKey(Handle, 1);
                if (down) UnregisterHotKey(Handle, 2);
                throw new Win32Exception(!up ? upError : downError,
                    "Could not reserve PgUp and PgDn. Exit another key mapper and try again.");
            }
            Enabled = true;
        }

        internal void Disable()
        {
            if (!Enabled) return;
            Enabled = false;
            UnregisterHotKey(Handle, 1); UnregisterHotKey(Handle, 2);
        }

        protected override void WndProc(ref Message message)
        {
            if (message.Msg == 0x0312 && Enabled)
            {
                if (message.WParam.ToInt32() == 1) onHotkey(0x25);
                if (message.WParam.ToInt32() == 2) onHotkey(0x27);
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
        bool extended = key == 0x25 || key == 0x27 || key == 0x5B || key == 0x21 || key == 0x22;
        return new Input { Type = 1, Data = new InputUnion { Keyboard = new KeyboardInput {
            Key = key, Flags = (up ? 2u : 0u) | (extended ? 1u : 0u), Extra = InputMarker } } };
    }
    internal static Input[] BuildShortcut(ushort arrow)
    {
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
            if (received[0] != 0x25 || received[1] != 0x27) throw new Exception("Incorrect hotkey dispatch.");
            foreach (ushort arrow in received)
            {
                Input[] events = BuildShortcut(arrow);
                ushort[] expectedKeys = { 0x5B, 0xA2, arrow, arrow, 0xA2, 0x5B };
                if (events.Length != 6) throw new Exception("Incorrect shortcut length.");
                for (int index = 0; index < events.Length; index++)
                    if (events[index].Type != 1 || events[index].Data.Keyboard.Key != expectedKeys[index] ||
                        ((events[index].Data.Keyboard.Flags & 2) != 0) != (index >= 3))
                        throw new Exception("Incorrect key sequence.");
            }
            window.Disable(); window.Enable(); window.Disable();
        }
        // Confirm exit/pause released both hotkeys by reserving them again.
        using (var window = new HotkeyWindow(delegate(ushort arrow) { }, delegate { })) window.Enable();
        File.WriteAllText(report, "PASS: native INPUT layout; real PgUp/PgDn injection and WM_HOTKEY routing; Win+Ctrl+Left/Right key-down/key-up sequences; pause/resume; registration cleanup. No desktop-switch shortcut was emitted.");
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
}
