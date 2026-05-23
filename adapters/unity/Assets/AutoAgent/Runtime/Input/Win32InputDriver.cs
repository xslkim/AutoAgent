using System.Collections;
using System.Runtime.InteropServices;
using UnityEngine;

namespace AutoAgent
{
    /// <summary>
    /// OS-layer input driver using the Win32 SendInput API.
    ///
    /// Supports Windows Editor (<c>UNITY_EDITOR_WIN</c>) and Windows standalone
    /// (<c>UNITY_STANDALONE_WIN</c>) builds only. On other platforms every
    /// method throws a <see cref="WireException"/> with code
    /// <see cref="WireError.InternalError"/>.
    ///
    /// Coordinate conversion:
    ///   Unity screen-space → Win32 ABSOLUTE (0–65535).
    ///   Accounts for the game-window's client-area origin (windowed mode) by
    ///   calling ClientToScreen on the process main-window handle, then
    ///   Y-flips (Unity Y=0 bottom ↔ Windows Y=0 top) and scales to 65535
    ///   across the virtual-screen dimensions.
    /// </summary>
    public static class Win32InputDriver
    {
        // Virtual key codes exposed so callers can reference them without magic numbers.
        public const ushort VK_RETURN = 0x0D;
        public const ushort VK_ESCAPE = 0x1B;
        public const ushort VK_TAB    = 0x09;
        public const ushort VK_SHIFT  = 0x10;

#if UNITY_STANDALONE_WIN || UNITY_EDITOR_WIN

        // ------------------------------------------------------------------
        // Win32 type constants
        // ------------------------------------------------------------------

        const int  INPUT_MOUSE    = 0;
        const int  INPUT_KEYBOARD = 1;

        const uint MOUSEEVENTF_MOVE       = 0x0001;
        const uint MOUSEEVENTF_LEFTDOWN   = 0x0002;
        const uint MOUSEEVENTF_LEFTUP     = 0x0004;
        const uint MOUSEEVENTF_RIGHTDOWN  = 0x0008;
        const uint MOUSEEVENTF_RIGHTUP    = 0x0010;
        const uint MOUSEEVENTF_MIDDLEDOWN = 0x0020;
        const uint MOUSEEVENTF_MIDDLEUP   = 0x0040;
        const uint MOUSEEVENTF_WHEEL      = 0x0800;
        const uint MOUSEEVENTF_ABSOLUTE   = 0x8000;

        const uint KEYEVENTF_KEYUP = 0x0002;

        const int WHEEL_DELTA        = 120;
        const int SM_CXVIRTUALSCREEN = 78;
        const int SM_CYVIRTUALSCREEN = 79;

        // ------------------------------------------------------------------
        // P/Invoke structs
        // ------------------------------------------------------------------

        [StructLayout(LayoutKind.Sequential)]
        struct MOUSEINPUT
        {
            public int   dx, dy;
            public uint  mouseData, dwFlags, time;
            public System.IntPtr dwExtraInfo;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct KEYBDINPUT
        {
            public ushort wVk, wScan;
            public uint   dwFlags, time;
            public System.IntPtr dwExtraInfo;
        }

        [StructLayout(LayoutKind.Explicit)]
        struct INPUTUNION
        {
            [FieldOffset(0)] public MOUSEINPUT  mi;
            [FieldOffset(0)] public KEYBDINPUT  ki;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct INPUT
        {
            public uint       type;
            public INPUTUNION data;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct POINT { public int X, Y; }

        // ------------------------------------------------------------------
        // P/Invoke declarations
        // ------------------------------------------------------------------

        [DllImport("user32.dll", SetLastError = true)]
        static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);

        [DllImport("user32.dll")]
        static extern int GetSystemMetrics(int nIndex);

        [DllImport("user32.dll")]
        static extern bool ClientToScreen(System.IntPtr hWnd, ref POINT lpPoint);

        // ------------------------------------------------------------------
        // Coordinate conversion
        // ------------------------------------------------------------------

        /// <summary>
        /// Convert a Unity screen-space position (bottom-left origin, pixels)
        /// to Win32 ABSOLUTE mouse coordinates (0–65535 range, top-left origin,
        /// scaled across the virtual screen).
        /// </summary>
        public static (int ax, int ay) ToAbsolute(Vector2 unityPos)
        {
            // Resolve the client-area origin on the Windows desktop.
            var hwnd = System.Diagnostics.Process.GetCurrentProcess().MainWindowHandle;
            var pt   = new POINT { X = 0, Y = 0 };
            ClientToScreen(hwnd, ref pt);       // pt = top-left of client area in screen coords
            int clientH = Screen.height;         // Unity client area height in pixels

            // Y-flip: Unity counts Y from the bottom, Windows from the top.
            int winX = pt.X + (int)unityPos.x;
            int winY = pt.Y + (clientH - 1 - (int)unityPos.y);

            int vw = GetSystemMetrics(SM_CXVIRTUALSCREEN);
            int vh = GetSystemMetrics(SM_CYVIRTUALSCREEN);
            // Guard against zero (e.g. headless CI) to avoid divide-by-zero.
            if (vw <= 0) vw = 1;
            if (vh <= 0) vh = 1;

            int ax = (int)((long)winX * 65535 / vw);
            int ay = (int)((long)winY * 65535 / vh);
            return (ax, ay);
        }

        // ------------------------------------------------------------------
        // Public actions
        // ------------------------------------------------------------------

        /// <summary>
        /// Move the cursor to <paramref name="unityPos"/> and send a mouse
        /// button down + up event.
        /// </summary>
        public static void Click(Vector2 unityPos, string button = "left")
        {
            var (ax, ay) = ToAbsolute(unityPos);
            uint downF, upF;
            switch (button)
            {
                case "right":  downF = MOUSEEVENTF_RIGHTDOWN;  upF = MOUSEEVENTF_RIGHTUP;  break;
                case "middle": downF = MOUSEEVENTF_MIDDLEDOWN; upF = MOUSEEVENTF_MIDDLEUP; break;
                default:       downF = MOUSEEVENTF_LEFTDOWN;   upF = MOUSEEVENTF_LEFTUP;   break;
            }
            SendInput(3, new[]
            {
                MakeMouse(ax, ay, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE),
                MakeMouse(ax, ay, 0, downF            | MOUSEEVENTF_ABSOLUTE),
                MakeMouse(ax, ay, 0, upF              | MOUSEEVENTF_ABSOLUTE),
            }, Marshal.SizeOf<INPUT>());
        }

        /// <summary>
        /// Coroutine that moves the cursor from <paramref name="fromPos"/> to
        /// <paramref name="toPos"/>, holding the left button down the entire
        /// time.  One MOUSEMOVE event is sent per frame.
        /// </summary>
        public static IEnumerator Drag(Vector2 fromPos, Vector2 toPos, int durationMs)
        {
            int frames = Mathf.Max(1,
                Mathf.RoundToInt(durationMs / EngineInputDriver.MillisPerDragStep));

            var (ax0, ay0) = ToAbsolute(fromPos);
            var (ax1, ay1) = ToAbsolute(toPos);

            SendOne(MakeMouse(ax0, ay0, 0, MOUSEEVENTF_MOVE     | MOUSEEVENTF_ABSOLUTE));
            SendOne(MakeMouse(ax0, ay0, 0, MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE));

            for (int i = 1; i <= frames; i++)
            {
                float t  = (float)i / frames;
                int   cx = (int)Mathf.Lerp(ax0, ax1, t);
                int   cy = (int)Mathf.Lerp(ay0, ay1, t);
                SendOne(MakeMouse(cx, cy, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE));
                yield return null;
            }

            SendOne(MakeMouse(ax1, ay1, 0, MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE));
        }

        /// <summary>
        /// Send a scroll-wheel event at <paramref name="unityPos"/>.
        /// <paramref name="delta"/> is in WHEEL_DELTA units: positive = scroll
        /// up (toward user), negative = scroll down.
        /// </summary>
        public static void Scroll(Vector2 unityPos, float delta)
        {
            var (ax, ay) = ToAbsolute(unityPos);
            // Negative delta wraps as unsigned — that is the correct Win32 behaviour.
            uint wheelData = unchecked((uint)(int)(delta * WHEEL_DELTA));
            SendOne(MakeMouse(ax, ay, wheelData,
                MOUSEEVENTF_MOVE | MOUSEEVENTF_WHEEL | MOUSEEVENTF_ABSOLUTE));
        }

        /// <summary>Send a virtual-key press (key-down followed by key-up).</summary>
        public static void KeyPress(ushort vkCode)
        {
            SendInput(2, new[]
            {
                MakeKey(vkCode, 0),
                MakeKey(vkCode, KEYEVENTF_KEYUP),
            }, Marshal.SizeOf<INPUT>());
        }

        /// <summary>
        /// Send a Shift+Tab chord (Shift-down, Tab-down, Tab-up, Shift-up).
        /// </summary>
        public static void ShiftTab()
        {
            SendInput(4, new[]
            {
                MakeKey(VK_SHIFT, 0),
                MakeKey(VK_TAB,   0),
                MakeKey(VK_TAB,   KEYEVENTF_KEYUP),
                MakeKey(VK_SHIFT, KEYEVENTF_KEYUP),
            }, Marshal.SizeOf<INPUT>());
        }

        // ------------------------------------------------------------------
        // Helpers
        // ------------------------------------------------------------------

        static void SendOne(INPUT inp) =>
            SendInput(1, new[] { inp }, Marshal.SizeOf<INPUT>());

        static INPUT MakeMouse(int dx, int dy, uint data, uint flags) => new INPUT
        {
            type = INPUT_MOUSE,
            data = new INPUTUNION
            {
                mi = new MOUSEINPUT
                {
                    dx = dx, dy = dy, mouseData = data, dwFlags = flags
                }
            }
        };

        static INPUT MakeKey(ushort vk, uint flags) => new INPUT
        {
            type = INPUT_KEYBOARD,
            data = new INPUTUNION { ki = new KEYBDINPUT { wVk = vk, dwFlags = flags } }
        };

#else
        // ------------------------------------------------------------------
        // Non-Windows stubs
        // ------------------------------------------------------------------

        static WireException NotWindows() => new WireException(
            WireError.InternalError,
            "os input_layer requires UNITY_STANDALONE_WIN or UNITY_EDITOR_WIN");

        /// <summary>Not available on non-Windows platforms.</summary>
        public static (int ax, int ay) ToAbsolute(Vector2 _) => throw NotWindows();

        /// <summary>Not available on non-Windows platforms.</summary>
        public static void Click(Vector2 _pos, string _btn = "left") => throw NotWindows();

        /// <summary>Not available on non-Windows platforms.</summary>
        public static IEnumerator Drag(Vector2 _from, Vector2 _to, int _ms = 100)
        { throw NotWindows(); yield break; }

        /// <summary>Not available on non-Windows platforms.</summary>
        public static void Scroll(Vector2 _pos, float _delta) => throw NotWindows();

        /// <summary>Not available on non-Windows platforms.</summary>
        public static void KeyPress(ushort _vk) => throw NotWindows();

        /// <summary>Not available on non-Windows platforms.</summary>
        public static void ShiftTab() => throw NotWindows();
#endif

        // ------------------------------------------------------------------
        // Key string → VK code mapping (platform-independent helper)
        // ------------------------------------------------------------------

        /// <summary>
        /// Map a protocol key string to the matching Win32 virtual-key code.
        /// </summary>
        /// <exception cref="WireException">
        /// Code <see cref="WireError.InvalidParams"/> for unrecognised keys.
        /// </exception>
        public static ushort MapKey(string key)
        {
            switch (key?.Trim().ToLowerInvariant())
            {
                case "enter":
                case "return":
                case "submit":  return VK_RETURN;
                case "escape":
                case "esc":
                case "cancel":  return VK_ESCAPE;
                case "tab":     return VK_TAB;
                default:
                    throw new WireException(WireError.InvalidParams,
                        $"unsupported key for os input_layer: {key}");
            }
        }
    }
}
