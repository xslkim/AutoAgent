using System.Collections;
using System.Runtime.InteropServices;
using UnityEngine;

namespace AutoAgent
{
    /// <summary>
    /// OS-layer input driver using the X11 XTest extension.
    ///
    /// Supports Linux Editor (<c>UNITY_EDITOR_LINUX</c>) and Linux standalone
    /// (<c>UNITY_STANDALONE_LINUX</c>) builds only. On other platforms every
    /// method throws a <see cref="WireException"/> with code
    /// <see cref="WireError.InternalError"/>.
    ///
    /// Coordinate conversion:
    ///   Unity screen-space → X11 screen coordinates.
    ///   X11 has (0,0) at top-left, Unity at bottom-left — Y-flip applied.
    ///   Display dimensions are queried from XDisplayWidth / XDisplayHeight.
    ///
    /// Requires an X11 session (XWayland is also supported; pure Wayland is not).
    /// </summary>
    public static class LinuxInputDriver
    {
        // X11 keycode constants (evdev driver, US keyboard layout).
        public const uint XK_RETURN = 36;
        public const uint XK_ESCAPE = 9;
        public const uint XK_TAB    = 23;
        public const uint XK_LSHIFT = 50;

#if UNITY_STANDALONE_LINUX || UNITY_EDITOR_LINUX

        // ------------------------------------------------------------------
        // X11 / XTest P/Invoke
        // ------------------------------------------------------------------

        const string LIBX11  = "libX11.so.6";
        const string LIBXTST = "libXtst.so.6";

        [DllImport(LIBX11)]
        static extern System.IntPtr XOpenDisplay(System.IntPtr displayName);

        [DllImport(LIBX11)]
        static extern int XFlush(System.IntPtr display);

        [DllImport(LIBX11)]
        static extern int XDisplayWidth(System.IntPtr display, int screen);

        [DllImport(LIBX11)]
        static extern int XDisplayHeight(System.IntPtr display, int screen);

        [DllImport(LIBX11)]
        static extern int XDefaultScreen(System.IntPtr display);

        [DllImport(LIBXTST)]
        static extern int XTestFakeMotionEvent(
            System.IntPtr display, int screen, int x, int y, ulong delay);

        [DllImport(LIBXTST)]
        static extern int XTestFakeButtonEvent(
            System.IntPtr display, uint button, bool isPress, ulong delay);

        [DllImport(LIBXTST)]
        static extern int XTestFakeKeyEvent(
            System.IntPtr display, uint keycode, bool isPress, ulong delay);

        // ------------------------------------------------------------------
        // Persistent X11 Display connection
        // ------------------------------------------------------------------

        static System.IntPtr _display;
        static readonly object _displayLock = new object();

        static System.IntPtr Display
        {
            get
            {
                if (_display == System.IntPtr.Zero)
                {
                    lock (_displayLock)
                    {
                        if (_display == System.IntPtr.Zero)
                        {
                            _display = XOpenDisplay(System.IntPtr.Zero);
                            if (_display == System.IntPtr.Zero)
                                throw new WireException(WireError.InternalError,
                                    "XOpenDisplay failed — is an X server running?");
                        }
                    }
                }
                return _display;
            }
        }

        static int DefaultScreen => XDefaultScreen(Display);

        // ------------------------------------------------------------------
        // Coordinate conversion
        // ------------------------------------------------------------------

        /// <summary>
        /// Convert a Unity screen-space position (bottom-left origin, pixels)
        /// to X11 screen coordinates (top-left origin, pixels).
        /// </summary>
        public static (int x, int y) ToX11Coords(Vector2 unityPos)
        {
            var dpy = Display;
            int scr = DefaultScreen;
            int displayH = XDisplayHeight(dpy, scr);
            int displayW = XDisplayWidth(dpy, scr);

            // X11 (0,0) = top-left, Unity (0,0) = bottom-left.
            int x = (int)unityPos.x;
            int y = displayH - 1 - (int)unityPos.y;

            x = Mathf.Max(0, Mathf.Min(x, displayW - 1));
            y = Mathf.Max(0, Mathf.Min(y, displayH - 1));
            return (x, y);
        }

        // ------------------------------------------------------------------
        // Public actions
        // ------------------------------------------------------------------

        /// <summary>
        /// Move the cursor to <paramref name="unityPos"/> and inject a mouse
        /// button press + release via XTestFakeButtonEvent.
        /// </summary>
        public static void Click(Vector2 unityPos, string button = "left")
        {
            var (x, y) = ToX11Coords(unityPos);
            var dpy = Display;
            int scr = DefaultScreen;

            uint btn = button switch
            {
                "right"  => 3u,
                "middle" => 2u,
                _        => 1u  // left
            };

            XTestFakeMotionEvent(dpy, scr, x, y, 0);
            XTestFakeButtonEvent(dpy, btn, true, 0);
            XTestFakeButtonEvent(dpy, btn, false, 0);
            XFlush(dpy);
        }

        /// <summary>
        /// Coroutine that moves the cursor from <paramref name="fromPos"/> to
        /// <paramref name="toPos"/>, holding the left button down.
        /// One motion event is injected per frame.
        /// </summary>
        public static IEnumerator Drag(Vector2 fromPos, Vector2 toPos,
                                       int durationMs)
        {
            int frames = Mathf.Max(1,
                Mathf.RoundToInt(durationMs / EngineInputDriver.MillisPerDragStep));

            var dpy = Display;
            int scr = DefaultScreen;
            var (x0, y0) = ToX11Coords(fromPos);
            var (x1, y1) = ToX11Coords(toPos);

            XTestFakeMotionEvent(dpy, scr, x0, y0, 0);
            XTestFakeButtonEvent(dpy, 1, true, 0);
            XFlush(dpy);

            for (int i = 1; i <= frames; i++)
            {
                float t = (float)i / frames;
                int cx = (int)Mathf.Lerp(x0, x1, t);
                int cy = (int)Mathf.Lerp(y0, y1, t);
                XTestFakeMotionEvent(dpy, scr, cx, cy, 0);
                XFlush(dpy);
                yield return null;
            }

            XTestFakeMotionEvent(dpy, scr, x1, y1, 0);
            XTestFakeButtonEvent(dpy, 1, false, 0);
            XFlush(dpy);
        }

        /// <summary>
        /// Move the cursor to <paramref name="unityPos"/> and send scroll
        /// events. X11 represents scroll as button-4 (up) / button-5 (down).
        /// <paramref name="delta"/>: positive = scroll up, negative = down.
        /// </summary>
        public static void Scroll(Vector2 unityPos, float delta)
        {
            var (x, y) = ToX11Coords(unityPos);
            var dpy = Display;
            int scr = DefaultScreen;

            XTestFakeMotionEvent(dpy, scr, x, y, 0);

            uint scrollButton = delta > 0 ? 4u : 5u;
            int clicks = System.Math.Max(1,
                System.Math.Abs((int)(delta * 3)));

            for (int i = 0; i < clicks; i++)
            {
                XTestFakeButtonEvent(dpy, scrollButton, true, 0);
                XTestFakeButtonEvent(dpy, scrollButton, false, 0);
            }
            XFlush(dpy);
        }

        /// <summary>Inject a key press (key-down followed by key-up).</summary>
        public static void KeyPress(uint x11Keycode)
        {
            var dpy = Display;
            XTestFakeKeyEvent(dpy, x11Keycode, true, 0);
            XTestFakeKeyEvent(dpy, x11Keycode, false, 0);
            XFlush(dpy);
        }

        /// <summary>
        /// Inject a Shift+Tab chord (Shift-down, Tab-down, Tab-up, Shift-up).
        /// </summary>
        public static void ShiftTab()
        {
            var dpy = Display;
            XTestFakeKeyEvent(dpy, XK_LSHIFT, true, 0);
            XTestFakeKeyEvent(dpy, XK_TAB, true, 0);
            XTestFakeKeyEvent(dpy, XK_TAB, false, 0);
            XTestFakeKeyEvent(dpy, XK_LSHIFT, false, 0);
            XFlush(dpy);
        }

#else
        // ------------------------------------------------------------------
        // Non-Linux stubs
        // ------------------------------------------------------------------

        static WireException NotLinux() => new WireException(
            WireError.InternalError,
            "os input_layer requires UNITY_STANDALONE_LINUX or UNITY_EDITOR_LINUX");

        /// <summary>Not available on non-Linux platforms.</summary>
        public static (int x, int y) ToX11Coords(Vector2 _) =>
            throw NotLinux();

        /// <summary>Not available on non-Linux platforms.</summary>
        public static void Click(Vector2 _pos, string _btn = "left") =>
            throw NotLinux();

        /// <summary>Not available on non-Linux platforms.</summary>
        public static IEnumerator Drag(Vector2 _from, Vector2 _to,
                                       int _ms = 100)
        { throw NotLinux(); }

        /// <summary>Not available on non-Linux platforms.</summary>
        public static void Scroll(Vector2 _pos, float _delta) =>
            throw NotLinux();

        /// <summary>Not available on non-Linux platforms.</summary>
        public static void KeyPress(uint _code) => throw NotLinux();

        /// <summary>Not available on non-Linux platforms.</summary>
        public static void ShiftTab() => throw NotLinux();
#endif

        // ------------------------------------------------------------------
        // Key string → X11 keycode mapping (platform-independent helper)
        // ------------------------------------------------------------------

        /// <summary>
        /// Map a protocol key string to the matching X11 keycode.
        /// </summary>
        /// <exception cref="WireException">
        /// Code <see cref="WireError.InvalidParams"/> for unrecognised keys.
        /// </exception>
        public static uint MapKey(string key)
        {
            switch (key?.Trim().ToLowerInvariant())
            {
                case "enter":
                case "return":
                case "submit":  return XK_RETURN;
                case "escape":
                case "esc":
                case "cancel":  return XK_ESCAPE;
                case "tab":     return XK_TAB;
                default:
                    throw new WireException(WireError.InvalidParams,
                        $"unsupported key for os input_layer: {key}");
            }
        }
    }
}
