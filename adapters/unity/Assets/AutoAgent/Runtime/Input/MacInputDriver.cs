using System.Collections;
using System.Runtime.InteropServices;
using UnityEngine;

namespace AutoAgent
{
    /// <summary>
    /// OS-layer input driver using macOS CoreGraphics (CGEventPost) API.
    ///
    /// Supports macOS Editor (<c>UNITY_EDITOR_OSX</c>) and macOS standalone
    /// (<c>UNITY_STANDALONE_OSX</c>) builds only. On other platforms every
    /// method throws a <see cref="WireException"/> with code
    /// <see cref="WireError.InternalError"/>.
    ///
    /// Coordinate conversion:
    ///   Unity screen-space → macOS global display coordinates.
    ///   macOS global coords have (0,0) at top-left of the main display,
    ///   so Y-flip is applied. Display bounds are queried from
    ///   CGDisplayBounds / CGMainDisplayID.
    ///
    /// macOS 10.14+ requires Accessibility permissions for CGEventPost to
    /// work. Without them, events are silently ignored by the system.
    /// </summary>
    public static class MacInputDriver
    {
        // macOS key code constants (CGKeyCode values, platform-independent).
        public const ushort CGKEY_RETURN = 0x24;   // 36
        public const ushort CGKEY_ESCAPE = 0x35;   // 53
        public const ushort CGKEY_TAB    = 0x30;   // 48
        public const ushort CGKEY_LSHIFT = 0x38;   // 56

#if UNITY_STANDALONE_OSX || UNITY_EDITOR_OSX

        // ------------------------------------------------------------------
        // CoreGraphics type constants
        // ------------------------------------------------------------------

        const string COREGRAPHICS =
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics";

        const uint kCGHIDEventTap          = 0;
        const uint kCGEventLeftMouseDown   = 1;
        const uint kCGEventLeftMouseUp     = 2;
        const uint kCGEventRightMouseDown  = 3;
        const uint kCGEventRightMouseUp    = 4;
        const uint kCGEventMouseMoved      = 5;
        const uint kCGEventLeftMouseDragged = 6;
        const uint kCGEventKeyDown         = 10;
        const uint kCGEventKeyUp           = 11;
        const uint kCGEventScrollWheel     = 22;
        const uint kCGEventOtherMouseDown  = 25;
        const uint kCGEventOtherMouseUp    = 26;

        const uint kCGMouseButtonLeft   = 0;
        const uint kCGMouseButtonRight  = 1;
        const uint kCGMouseButtonCenter = 2;

        // ------------------------------------------------------------------
        // P/Invoke structs
        // ------------------------------------------------------------------

        [StructLayout(LayoutKind.Sequential)]
        struct CGPoint { public double x, y; }

        [StructLayout(LayoutKind.Sequential)]
        struct CGSize { public double width, height; }

        [StructLayout(LayoutKind.Sequential)]
        struct CGRect
        {
            public CGPoint origin;
            public CGSize  size;
        }

        // ------------------------------------------------------------------
        // P/Invoke declarations
        // ------------------------------------------------------------------

        [DllImport(COREGRAPHICS)]
        static extern System.IntPtr CGEventCreateMouseEvent(
            System.IntPtr source, uint mouseType, CGPoint mousePosition,
            uint mouseButton);

        [DllImport(COREGRAPHICS)]
        static extern System.IntPtr CGEventCreateKeyboardEvent(
            System.IntPtr source, ushort virtualKey, bool keyDown);

        [DllImport(COREGRAPHICS)]
        static extern System.IntPtr CGEventCreateScrollWheelEvent(
            System.IntPtr source, uint units, uint wheelCount, int wheelDelta);

        [DllImport(COREGRAPHICS)]
        static extern void CGEventPost(uint tap, System.IntPtr evt);

        [DllImport(COREGRAPHICS)]
        static extern void CFRelease(System.IntPtr cf);

        [DllImport(COREGRAPHICS)]
        static extern CGRect CGDisplayBounds(uint displayID);

        [DllImport(COREGRAPHICS)]
        static extern uint CGMainDisplayID();

        // ------------------------------------------------------------------
        // Coordinate conversion
        // ------------------------------------------------------------------

        /// <summary>
        /// Convert a Unity screen-space position (bottom-left origin, pixels)
        /// to macOS global display coordinates (top-left origin, points).
        /// </summary>
        public static (double macX, double macY) ToScreenPoint(Vector2 unityPos)
        {
            var bounds  = CGDisplayBounds(CGMainDisplayID());
            double displayH = bounds.size.height;
            double displayW = bounds.size.width;

            // Y-flip: Unity Y=0 is bottom, macOS Y=0 is top.
            double macX = unityPos.x;
            double macY = displayH - unityPos.y;

            macX = System.Math.Max(0, System.Math.Min(macX, displayW));
            macY = System.Math.Max(0, System.Math.Min(macY, displayH));
            return (macX, macY);
        }

        // ------------------------------------------------------------------
        // Public actions
        // ------------------------------------------------------------------

        /// <summary>
        /// Move the cursor to <paramref name="unityPos"/> and inject a mouse
        /// button down + up event via CGEventPost.
        /// </summary>
        public static void Click(Vector2 unityPos, string button = "left")
        {
            var (mx, my) = ToScreenPoint(unityPos);
            var pt = new CGPoint { x = mx, y = my };

            uint downType, upType, buttonConst;
            switch (button)
            {
                case "right":
                    downType = kCGEventRightMouseDown; upType = kCGEventRightMouseUp;
                    buttonConst = kCGMouseButtonRight; break;
                case "middle":
                    downType = kCGEventOtherMouseDown; upType = kCGEventOtherMouseUp;
                    buttonConst = kCGMouseButtonCenter; break;
                default:
                    downType = kCGEventLeftMouseDown; upType = kCGEventLeftMouseUp;
                    buttonConst = kCGMouseButtonLeft; break;
            }

            PostAndRelease(CGEventCreateMouseEvent(System.IntPtr.Zero,
                kCGEventMouseMoved, pt, 0));
            PostAndRelease(CGEventCreateMouseEvent(System.IntPtr.Zero,
                downType, pt, buttonConst));
            PostAndRelease(CGEventCreateMouseEvent(System.IntPtr.Zero,
                upType, pt, buttonConst));
        }

        /// <summary>
        /// Coroutine that moves the cursor from <paramref name="fromPos"/> to
        /// <paramref name="toPos"/>, holding the left button down.
        /// One move event is injected per frame.
        /// </summary>
        public static IEnumerator Drag(Vector2 fromPos, Vector2 toPos,
                                       int durationMs)
        {
            int frames = Mathf.Max(1,
                Mathf.RoundToInt(durationMs / EngineInputDriver.MillisPerDragStep));

            var (fx, fy) = ToScreenPoint(fromPos);
            var (tx, ty) = ToScreenPoint(toPos);

            var fromPt = new CGPoint { x = fx, y = fy };

            PostAndRelease(CGEventCreateMouseEvent(System.IntPtr.Zero,
                kCGEventMouseMoved, fromPt, kCGMouseButtonLeft));
            PostAndRelease(CGEventCreateMouseEvent(System.IntPtr.Zero,
                kCGEventLeftMouseDown, fromPt, kCGMouseButtonLeft));

            for (int i = 1; i <= frames; i++)
            {
                float t = (float)i / frames;
                var curPt = new CGPoint
                {
                    x = fx + (tx - fx) * t,
                    y = fy + (ty - fy) * t
                };
                PostAndRelease(CGEventCreateMouseEvent(System.IntPtr.Zero,
                    kCGEventLeftMouseDragged, curPt, kCGMouseButtonLeft));
                yield return null;
            }

            var toPt = new CGPoint { x = tx, y = ty };
            PostAndRelease(CGEventCreateMouseEvent(System.IntPtr.Zero,
                kCGEventLeftMouseUp, toPt, kCGMouseButtonLeft));
        }

        /// <summary>
        /// Move the cursor to <paramref name="unityPos"/> and send a scroll
        /// wheel event. <paramref name="delta"/> is in scroll units: positive
        /// = scroll up, negative = scroll down.
        /// </summary>
        public static void Scroll(Vector2 unityPos, float delta)
        {
            var (mx, my) = ToScreenPoint(unityPos);
            var pt = new CGPoint { x = mx, y = my };

            // Move cursor to position first, then post scroll wheel.
            PostAndRelease(CGEventCreateMouseEvent(System.IntPtr.Zero,
                kCGEventMouseMoved, pt, 0));

            int wheelDelta = (int)(delta * 3);
            PostAndRelease(CGEventCreateScrollWheelEvent(
                System.IntPtr.Zero, 0 /* pixels */, 1, wheelDelta));
        }

        /// <summary>Inject a keyboard key-down followed by key-up.</summary>
        public static void KeyPress(ushort cgKeyCode)
        {
            PostAndRelease(CGEventCreateKeyboardEvent(
                System.IntPtr.Zero, cgKeyCode, true));
            PostAndRelease(CGEventCreateKeyboardEvent(
                System.IntPtr.Zero, cgKeyCode, false));
        }

        /// <summary>
        /// Inject a Shift+Tab chord (Shift-down, Tab-down, Tab-up, Shift-up).
        /// </summary>
        public static void ShiftTab()
        {
            PostAndRelease(CGEventCreateKeyboardEvent(
                System.IntPtr.Zero, CGKEY_LSHIFT, true));
            PostAndRelease(CGEventCreateKeyboardEvent(
                System.IntPtr.Zero, CGKEY_TAB, true));
            PostAndRelease(CGEventCreateKeyboardEvent(
                System.IntPtr.Zero, CGKEY_TAB, false));
            PostAndRelease(CGEventCreateKeyboardEvent(
                System.IntPtr.Zero, CGKEY_LSHIFT, false));
        }

        // ------------------------------------------------------------------
        // Helpers
        // ------------------------------------------------------------------

        static void PostAndRelease(System.IntPtr evt)
        {
            if (evt == System.IntPtr.Zero) return;
            CGEventPost(kCGHIDEventTap, evt);
            CFRelease(evt);
        }

#else
        // ------------------------------------------------------------------
        // Non-macOS stubs
        // ------------------------------------------------------------------

        static WireException NotMacOS() => new WireException(
            WireError.InternalError,
            "os input_layer requires UNITY_STANDALONE_OSX or UNITY_EDITOR_OSX");

        /// <summary>Not available on non-macOS platforms.</summary>
        public static (double macX, double macY) ToScreenPoint(Vector2 _) =>
            throw NotMacOS();

        /// <summary>Not available on non-macOS platforms.</summary>
        public static void Click(Vector2 _pos, string _btn = "left") =>
            throw NotMacOS();

        /// <summary>Not available on non-macOS platforms.</summary>
        public static IEnumerator Drag(Vector2 _from, Vector2 _to,
                                       int _ms = 100)
        { throw NotMacOS(); yield break; }

        /// <summary>Not available on non-macOS platforms.</summary>
        public static void Scroll(Vector2 _pos, float _delta) =>
            throw NotMacOS();

        /// <summary>Not available on non-macOS platforms.</summary>
        public static void KeyPress(ushort _code) => throw NotMacOS();

        /// <summary>Not available on non-macOS platforms.</summary>
        public static void ShiftTab() => throw NotMacOS();
#endif

        // ------------------------------------------------------------------
        // Key string → CGKeyCode mapping (platform-independent helper)
        // ------------------------------------------------------------------

        /// <summary>
        /// Map a protocol key string to the matching macOS CGKeyCode.
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
                case "submit":  return CGKEY_RETURN;
                case "escape":
                case "esc":
                case "cancel":  return CGKEY_ESCAPE;
                case "tab":     return CGKEY_TAB;
                default:
                    throw new WireException(WireError.InvalidParams,
                        $"unsupported key for os input_layer: {key}");
            }
        }
    }
}
