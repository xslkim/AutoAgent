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
    /// </summary>
    public static class EngineInputDriver
    {
        // ------------------------------------------------------------------ click

        /// <summary>
        /// Simulate a complete click on a node: PointerDown → PointerUp →
        /// PointerClick, the same sequence the EventSystem fires for a real
        /// mouse click, so every Selectable subclass (Button, Toggle, …) reacts.
        /// </summary>
        /// <exception cref="WireException">
        /// Code -32001 if the id resolves to no node; code -32002 if the node
        /// exists but has no component able to handle a click.
        /// </exception>
        public static void Click(string nodeId)
        {
            var go = ResolveClickable(nodeId);

            var eventData = NewPointerEvent(go);
            ExecuteEvents.Execute(go, eventData, ExecuteEvents.pointerDownHandler);
            ExecuteEvents.Execute(go, eventData, ExecuteEvents.pointerUpHandler);
            ExecuteEvents.Execute(go, eventData, ExecuteEvents.pointerClickHandler);
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
        /// Multi-frame drag coroutine: PointerDown → BeginDrag → N×Drag (one
        /// per frame) → EndDrag → Drop → PointerUp. Splitting OnDrag across
        /// frames avoids single-frame IDragHandler implementations misbehaving.
        /// </summary>
        /// <exception cref="WireException">
        /// Code -32001 if either id resolves to no node; code -32002 if the
        /// source has no drag handler.
        /// </exception>
        public static IEnumerator Drag(string fromId, string toId, int durationMs = 100)
        {
            var (src, dst) = ResolveDrag(fromId, toId);
            yield return DragSteps(src, dst, durationMs);
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

        // ------------------------------------------------------------------ scroll

        public static bool Scroll(string nodeId, float deltaX, float deltaY)
        {
            var go = FindById(nodeId);
            if (go == null) return false;

            // Try direct ScrollRect manipulation first (most reliable in PoC)
            var sr = go.GetComponent<ScrollRect>();
            if (sr == null) sr = go.GetComponentInParent<ScrollRect>();
            if (sr != null)
            {
                sr.normalizedPosition += new Vector2(deltaX, deltaY);
                return true;
            }

            // Fallback: synthetic scroll event
            var eventData = NewPointerEvent(go);
            eventData.scrollDelta = new Vector2(deltaX, deltaY);
            ExecuteEvents.Execute(go, eventData, ExecuteEvents.scrollHandler);
            return true;
        }

        // ------------------------------------------------------------------ helpers

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
