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

        public static bool Click(string nodeId)
        {
            var go = FindById(nodeId);
            if (go == null) return false;

            var eventData = NewPointerEvent(go);
            ExecuteEvents.Execute(go, eventData, ExecuteEvents.pointerDownHandler);
            ExecuteEvents.Execute(go, eventData, ExecuteEvents.pointerUpHandler);
            ExecuteEvents.Execute(go, eventData, ExecuteEvents.pointerClickHandler);
            return true;
        }

        // ------------------------------------------------------------------ drag

        public static bool Drag(string fromId, string toId)
        {
            var src = FindById(fromId);
            var dst = FindById(toId);
            if (src == null || dst == null) return false;

            var srcEvent = NewPointerEvent(src);
            var dstEvent = NewPointerEvent(dst);

            ExecuteEvents.Execute(src, srcEvent, ExecuteEvents.pointerDownHandler);
            ExecuteEvents.Execute(src, srcEvent, ExecuteEvents.beginDragHandler);
            // single-step move to destination (PoC: no intermediate frames)
            srcEvent.position = dstEvent.position;
            ExecuteEvents.Execute(src, srcEvent, ExecuteEvents.dragHandler);
            ExecuteEvents.Execute(src, srcEvent, ExecuteEvents.endDragHandler);
            ExecuteEvents.Execute(dst, dstEvent, ExecuteEvents.dropHandler);
            ExecuteEvents.Execute(src, srcEvent, ExecuteEvents.pointerUpHandler);
            return true;
        }

        // ------------------------------------------------------------------ send_text

        public static bool SendText(string nodeId, string text)
        {
            var go = FindById(nodeId);
            if (go == null) return false;

            var tmpIf = go.GetComponent<TMP_InputField>();
            if (tmpIf != null)
            {
                tmpIf.text = text;
                tmpIf.onEndEdit.Invoke(text);
                return true;
            }

            var legacyIf = go.GetComponent<InputField>();
            if (legacyIf != null)
            {
                legacyIf.text = text;
                legacyIf.onEndEdit.Invoke(text);
                return true;
            }

            return false;
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
