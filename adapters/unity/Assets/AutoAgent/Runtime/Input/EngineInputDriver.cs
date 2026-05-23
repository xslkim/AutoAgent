using System.Collections;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
using TMPro;

namespace AutoAgent
{
    /// <summary>
    /// Executes the four wire-protocol actions (click, drag, send_text, scroll)
    /// on UI elements located by their stable ID.
    /// All public methods must be called from the Unity main thread.
    ///
    /// <para><b>input_layer</b>: pass <c>"engine"</c> (default) to use Unity's
    /// EventSystem, or <c>"os"</c> to inject OS-level input via
    /// <see cref="Win32InputDriver"/> (Windows only).</para>
    /// </summary>
    public static class EngineInputDriver
    {
        // ------------------------------------------------------------------ click

        /// <summary>
        /// Simulate a click on a node.
        ///
        /// <para><c>inputLayer="engine"</c> (default): fires PointerDown →
        /// PointerUp → PointerClick via Unity's EventSystem.</para>
        /// <para><c>inputLayer="os"</c>: moves the OS cursor to the node's
        /// screen position and sends Win32 SendInput mouse events (Windows only).
        /// No component-interactability check is performed.</para>
        /// </summary>
        /// <exception cref="WireException">
        /// Code -32001 if the id resolves to no node; code -32002 if the node
        /// exists but has no clickable component (engine layer only).
        /// </exception>
        public static void Click(string nodeId,
                                 string inputLayer = "engine",
                                 string button     = "left")
        {
            if (inputLayer == "os")
            {
                var go  = FindById(nodeId);
                if (go == null)
                    throw new WireException(WireError.WidgetNotFound,
                        $"widget not found: {nodeId}");
                var pos = GetScreenPosition(go);
                if (pos == null)
                    throw new WireException(WireError.WidgetNotInteractable,
                        $"widget has no RectTransform (required for os input): {nodeId}");
#if UNITY_STANDALONE_WIN || UNITY_EDITOR_WIN
                Win32InputDriver.Click(pos.Value, button);
#elif UNITY_STANDALONE_OSX || UNITY_EDITOR_OSX
                MacInputDriver.Click(pos.Value, button);
#elif UNITY_STANDALONE_LINUX || UNITY_EDITOR_LINUX
                LinuxInputDriver.Click(pos.Value, button);
#else
                throw new WireException(WireError.InternalError,
                    "os input_layer requires Windows, macOS, or Linux");
#endif
                return;
            }

            var clickable  = ResolveClickable(nodeId);
            var eventData  = NewPointerEvent(clickable);
            ExecuteEvents.Execute(clickable, eventData, ExecuteEvents.pointerDownHandler);
            ExecuteEvents.Execute(clickable, eventData, ExecuteEvents.pointerUpHandler);
            ExecuteEvents.Execute(clickable, eventData, ExecuteEvents.pointerClickHandler);
        }

        // Resolve a node id to a GameObject that can actually receive a click,
        // or throw the matching WireException.
        static GameObject ResolveClickable(string nodeId)
        {
            var go = FindById(nodeId);
            if (go == null)
                throw new WireException(WireError.WidgetNotFound,
                    $"widget not found: {nodeId}");
            if (!IsClickable(go))
                throw new WireException(WireError.WidgetNotInteractable,
                    $"widget has no clickable component: {nodeId}");
            return go;
        }

        // A node is clickable if it carries a Selectable (Button / Toggle / …)
        // or any MonoBehaviour implementing an EventSystems pointer handler.
        static bool IsClickable(GameObject go)
        {
            if (go.GetComponent<Selectable>() != null)
                return true;
            foreach (var mb in go.GetComponents<MonoBehaviour>())
            {
                if (mb == null) continue;
                if (mb is IPointerClickHandler ||
                    mb is IPointerDownHandler ||
                    mb is IPointerUpHandler)
                    return true;
            }
            return false;
        }

        // ------------------------------------------------------------------ drag

        /// <summary>Frame budget per OnDrag step (~60 fps). Drag spans
        /// duration_ms / this many frames.</summary>
        public const float MillisPerDragStep = 16f;

        /// <summary>Number of OnDrag frames a drag of the given duration spans.</summary>
        public static int FrameCountFor(int durationMs) =>
            Mathf.Max(1, Mathf.RoundToInt(durationMs / MillisPerDragStep));

        /// <summary>
        /// Multi-frame drag coroutine.
        ///
        /// <para><c>inputLayer="engine"</c> (default): PointerDown → BeginDrag
        /// → N×Drag → EndDrag → Drop → PointerUp via Unity's EventSystem.
        /// Requires the source to implement a drag handler.</para>
        /// <para><c>inputLayer="os"</c>: moves the OS cursor with SendInput
        /// (Windows only). No drag-handler check is performed.</para>
        /// </summary>
        /// <exception cref="WireException">
        /// Code -32001 if either id resolves to no node; code -32002 if the
        /// source has no drag handler (engine layer only).
        /// </exception>
        public static IEnumerator Drag(string fromId, string toId,
                                       int durationMs = 100,
                                       string inputLayer = "engine")
        {
            if (inputLayer == "os")
            {
                var src = FindById(fromId);
                if (src == null)
                    throw new WireException(WireError.WidgetNotFound,
                        $"drag source not found: {fromId}");
                var dst = FindById(toId);
                if (dst == null)
                    throw new WireException(WireError.WidgetNotFound,
                        $"drag target not found: {toId}");
                var fromPos = GetScreenPosition(src);
                var toPos   = GetScreenPosition(dst);
                if (fromPos == null)
                    throw new WireException(WireError.WidgetNotInteractable,
                        $"drag source has no RectTransform: {fromId}");
                if (toPos == null)
                    throw new WireException(WireError.WidgetNotInteractable,
                        $"drag target has no RectTransform: {toId}");
#if UNITY_STANDALONE_WIN || UNITY_EDITOR_WIN
                yield return Win32InputDriver.Drag(fromPos.Value, toPos.Value, durationMs);
#elif UNITY_STANDALONE_OSX || UNITY_EDITOR_OSX
                yield return MacInputDriver.Drag(fromPos.Value, toPos.Value, durationMs);
#elif UNITY_STANDALONE_LINUX || UNITY_EDITOR_LINUX
                yield return LinuxInputDriver.Drag(fromPos.Value, toPos.Value, durationMs);
#else
                throw new WireException(WireError.InternalError,
                    "os input_layer requires Windows, macOS, or Linux");
#endif
                yield break;
            }

            var (engineSrc, engineDst) = ResolveDrag(fromId, toId);
            yield return DragSteps(engineSrc, engineDst, durationMs);
        }

        // Synchronously resolve + validate the two endpoints, or throw.
        internal static (GameObject src, GameObject dst) ResolveDrag(string fromId, string toId)
        {
            var src = FindById(fromId);
            if (src == null)
                throw new WireException(WireError.WidgetNotFound,
                    $"drag source not found: {fromId}");
            var dst = FindById(toId);
            if (dst == null)
                throw new WireException(WireError.WidgetNotFound,
                    $"drag target not found: {toId}");
            if (!IsDraggable(src))
                throw new WireException(WireError.WidgetNotInteractable,
                    $"widget has no drag handler: {fromId}");
            return (src, dst);
        }

        static bool IsDraggable(GameObject go)
        {
            foreach (var mb in go.GetComponents<MonoBehaviour>())
            {
                if (mb == null) continue;
                if (mb is IBeginDragHandler || mb is IDragHandler)
                    return true;
            }
            return false;
        }

        internal static IEnumerator DragSteps(GameObject src, GameObject dst, int durationMs)
        {
            int frames = FrameCountFor(durationMs);
            var srcEvent = NewPointerEvent(src);
            var dstEvent = NewPointerEvent(dst);
            Vector2 startPos = srcEvent.position;
            Vector2 endPos = dstEvent.position;

            ExecuteEvents.Execute(src, srcEvent, ExecuteEvents.pointerDownHandler);
            ExecuteEvents.Execute(src, srcEvent, ExecuteEvents.beginDragHandler);

            Vector2 prev = startPos;
            for (int i = 1; i <= frames; i++)
            {
                Vector2 cur = Vector2.Lerp(startPos, endPos, (float)i / frames);
                srcEvent.position = cur;
                srcEvent.delta = cur - prev;
                prev = cur;
                ExecuteEvents.Execute(src, srcEvent, ExecuteEvents.dragHandler);
                yield return null; // advance one frame between OnDrag steps
            }

            srcEvent.position = endPos;
            ExecuteEvents.Execute(src, srcEvent, ExecuteEvents.endDragHandler);

            dstEvent.position = endPos;
            dstEvent.pointerDrag = src;
            ExecuteEvents.Execute(dst, dstEvent, ExecuteEvents.dropHandler);

            ExecuteEvents.Execute(src, srcEvent, ExecuteEvents.pointerUpHandler);
        }

        // ------------------------------------------------------------------ send_text

        /// <summary>
        /// Set text on a TMP_InputField or legacy InputField. When
        /// <paramref name="clearFirst"/> is true (default) the field's old
        /// value is replaced; when false the text is appended.
        ///
        /// Fires onValueChanged then onEndEdit, matching what a real user
        /// edit + focus-loss produces. Uses SetTextWithoutNotify so the
        /// notifications fire exactly once.
        /// </summary>
        /// <exception cref="WireException">
        /// Code -32001 if the id resolves to no node; code -32002 if the node
        /// is not a text input field.
        /// </exception>
        public static void SendText(string nodeId, string text, bool clearFirst = true)
        {
            var go = FindById(nodeId);
            if (go == null)
                throw new WireException(WireError.WidgetNotFound,
                    $"widget not found: {nodeId}");

            text ??= "";

            var tmpIf = go.GetComponent<TMP_InputField>();
            if (tmpIf != null)
            {
                string value = clearFirst ? text : (tmpIf.text ?? "") + text;
                tmpIf.SetTextWithoutNotify(value);
                tmpIf.onValueChanged.Invoke(value);
                tmpIf.onEndEdit.Invoke(value);
                return;
            }

            var legacyIf = go.GetComponent<InputField>();
            if (legacyIf != null)
            {
                string value = clearFirst ? text : (legacyIf.text ?? "") + text;
                legacyIf.SetTextWithoutNotify(value);
                legacyIf.onValueChanged.Invoke(value);
                legacyIf.onEndEdit.Invoke(value);
                return;
            }

            throw new WireException(WireError.WidgetNotInteractable,
                $"widget is not a text input field: {nodeId}");
        }

        // ------------------------------------------------------------------ key_press

        /// <summary>
        /// Send a key event to a node.
        ///
        /// <para><c>inputLayer="engine"</c> (default): dispatches Unity
        /// EventSystem events. Supported keys:
        ///   Enter/Return/Submit → ISubmitHandler.OnSubmit;
        ///   Escape/Cancel       → ICancelHandler.OnCancel;
        ///   Tab                 → focus next Selectable;
        ///   Shift+Tab/ShiftTab  → focus previous Selectable.</para>
        /// <para><c>inputLayer="os"</c>: sends Win32 SendInput virtual-key
        /// events (Windows only). Supported keys: Enter, Escape, Tab,
        /// Shift+Tab. The <paramref name="nodeId"/> must resolve to a node
        /// with a RectTransform (for screen position), but no handler check is
        /// performed.</para>
        /// </summary>
        /// <exception cref="WireException">
        /// Code -32001 if the id resolves to no node;
        /// code -32002 if the node has no handler for the key (engine only);
        /// code -32602 if <paramref name="key"/> is not a supported value.
        /// </exception>
        public static void KeyPress(string nodeId, string key,
                                    string inputLayer = "engine")
        {
            var go = FindById(nodeId);
            if (go == null)
                throw new WireException(WireError.WidgetNotFound,
                    $"widget not found: {nodeId}");
            if (string.IsNullOrEmpty(key))
                throw new WireException(WireError.InvalidParams, "key is required");

            if (inputLayer == "os")
            {
                string k = key.Trim().ToLowerInvariant();
                if (k == "shifttab" || k == "shift+tab")
                {
#if UNITY_STANDALONE_WIN || UNITY_EDITOR_WIN
                    Win32InputDriver.ShiftTab();
#elif UNITY_STANDALONE_OSX || UNITY_EDITOR_OSX
                    MacInputDriver.ShiftTab();
#elif UNITY_STANDALONE_LINUX || UNITY_EDITOR_LINUX
                    LinuxInputDriver.ShiftTab();
#else
                    throw new WireException(WireError.InternalError,
                        "os input_layer requires Windows, macOS, or Linux");
#endif
                }
                else
                {
#if UNITY_STANDALONE_WIN || UNITY_EDITOR_WIN
                    ushort vk = Win32InputDriver.MapKey(key);
                    Win32InputDriver.KeyPress(vk);
#elif UNITY_STANDALONE_OSX || UNITY_EDITOR_OSX
                    ushort ck = MacInputDriver.MapKey(key);
                    MacInputDriver.KeyPress(ck);
#elif UNITY_STANDALONE_LINUX || UNITY_EDITOR_LINUX
                    uint xk = LinuxInputDriver.MapKey(key);
                    LinuxInputDriver.KeyPress(xk);
#else
                    throw new WireException(WireError.InternalError,
                        "os input_layer requires Windows, macOS, or Linux");
#endif
                }
                return;
            }

            switch (key.Trim().ToLowerInvariant())
            {
                case "enter":
                case "return":
                case "submit":
                    DispatchSubmit(go);
                    break;
                case "escape":
                case "esc":
                case "cancel":
                    DispatchCancel(go);
                    break;
                case "tab":
                    FocusNeighbor(go, reverse: false);
                    break;
                case "shifttab":
                case "shift+tab":
                    FocusNeighbor(go, reverse: true);
                    break;
                default:
                    throw new WireException(WireError.InvalidParams,
                        $"unsupported key: {key}");
            }
        }

        static void DispatchSubmit(GameObject go)
        {
            if (!HasInterface<ISubmitHandler>(go))
                throw new WireException(WireError.WidgetNotInteractable,
                    $"widget has no ISubmitHandler (cannot accept Enter): {go.name}");
            var data = new BaseEventData(EventSystem.current);
            ExecuteEvents.Execute(go, data, ExecuteEvents.submitHandler);
        }

        static void DispatchCancel(GameObject go)
        {
            if (!HasInterface<ICancelHandler>(go))
                throw new WireException(WireError.WidgetNotInteractable,
                    $"widget has no ICancelHandler (cannot accept Escape): {go.name}");
            var data = new BaseEventData(EventSystem.current);
            ExecuteEvents.Execute(go, data, ExecuteEvents.cancelHandler);
        }

        // Tab navigation: pick the next/previous Selectable from the global
        // Selectable registry and tell the EventSystem to focus it.
        static void FocusNeighbor(GameObject go, bool reverse)
        {
            var sel = go.GetComponent<Selectable>();
            if (sel == null)
                throw new WireException(WireError.WidgetNotInteractable,
                    $"widget has no Selectable (cannot Tab from): {go.name}");

            int count = Selectable.allSelectableCount;
            if (count <= 1) return; // nothing else to move to — no-op
            var all = new Selectable[count];
            Selectable.AllSelectablesNoAlloc(all);
            int idx = System.Array.IndexOf(all, sel);
            if (idx < 0) return;
            int nextIdx = reverse ? (idx - 1 + count) % count : (idx + 1) % count;
            var next = all[nextIdx];
            if (next == null) return;

            var es = EventSystem.current;
            if (es != null) es.SetSelectedGameObject(next.gameObject);
        }

        static bool HasInterface<T>(GameObject go) where T : class
        {
            foreach (var mb in go.GetComponents<MonoBehaviour>())
                if (mb is T) return true;
            return false;
        }

        // ------------------------------------------------------------------ scroll

        /// <summary>
        /// Scroll the node's enclosing ScrollRect by (deltaX, deltaY) in
        /// normalized-position units. Looks up the ScrollRect on the node
        /// itself first, then walks up to a parent — addressing either the
        /// viewport / content child or the ScrollRect root works.
        ///
        /// Setting <c>normalizedPosition</c> triggers
        /// <c>ScrollRect.onValueChanged</c>; Unity clamps the value to [0,1].
        /// </summary>
        /// <exception cref="WireException">
        /// Code -32001 if the id resolves to no node; code -32002 if the node
        /// (and no ancestor) carries a ScrollRect.
        /// </exception>
        public static void Scroll(string nodeId, float deltaX, float deltaY)
        {
            var go = FindById(nodeId);
            if (go == null)
                throw new WireException(WireError.WidgetNotFound,
                    $"widget not found: {nodeId}");

            var sr = go.GetComponent<ScrollRect>();
            if (sr == null) sr = go.GetComponentInParent<ScrollRect>();
            if (sr == null)
                throw new WireException(WireError.WidgetNotInteractable,
                    $"widget has no ScrollRect (self or ancestor): {nodeId}");

            sr.normalizedPosition += new Vector2(deltaX, deltaY);
        }

        // ------------------------------------------------------------------ helpers

        /// <summary>
        /// Return the Unity screen-space position of <paramref name="go"/>'s
        /// RectTransform, or <c>null</c> if the object has no RectTransform.
        /// </summary>
        internal static Vector2? GetScreenPosition(GameObject go)
        {
            var rt = go?.GetComponent<RectTransform>();
            if (rt == null) return null;
            var cam = FindCanvasCamera(rt);
            return RectTransformUtility.WorldToScreenPoint(cam, rt.position);
        }

        static PointerEventData NewPointerEvent(GameObject go)
        {
            var es = EventSystem.current;
            var rt = go.GetComponent<RectTransform>();
            var cam = rt != null ? FindCanvasCamera(rt) : null;

            var pos = rt != null
                ? RectTransformUtility.WorldToScreenPoint(cam, rt.position)
                : Vector2.zero;

            var ed = new PointerEventData(es) { position = pos };
            ed.pointerPressRaycast = new RaycastResult { gameObject = go };
            ed.pointerPress = go;
            return ed;
        }

        static Camera FindCanvasCamera(RectTransform rt)
        {
            var canvas = rt.GetComponentInParent<Canvas>();
            if (canvas == null) return null;
            return canvas.renderMode == RenderMode.ScreenSpaceOverlay ? null : canvas.worldCamera;
        }

        internal static GameObject FindById(string id)
        {
            if (string.IsNullOrEmpty(id)) return null;

            // Resolve through the same allocator dump_tree uses, so an id
            // handed back by dump_tree (pinned or hash) always resolves here.
            var roots = UnityEngine.SceneManagement.SceneManager
                .GetActiveScene().GetRootGameObjects();
            var allocator = IdAllocator.Allocate(roots);
            var t = allocator.TransformFor(id);
            if (t != null) return t.gameObject;

            // Fallbacks for callers that pass a raw pinnedId / GameObject name
            // before a dump has happened.
            var sids = Object.FindObjectsByType<StableIdComponent>(FindObjectsSortMode.None);
            foreach (var s in sids)
                if (s.pinnedId == id) return s.gameObject;
            return GameObject.Find(id);
        }
    }
}
