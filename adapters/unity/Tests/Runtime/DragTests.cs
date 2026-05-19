using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace AutoAgent.Tests
{
    /// <summary>
    /// PlayMode tests for EngineInputDriver.Drag (TASK-0107).
    /// Drag is a multi-frame coroutine: BeginDrag → N×Drag → EndDrag → Drop.
    /// </summary>
    public class DragTests
    {
        GameObject _canvas;

        [SetUp]
        public void SetUp()
        {
            _canvas = new GameObject("DragTestCanvas");
            var c = _canvas.AddComponent<Canvas>();
            c.renderMode = RenderMode.ScreenSpaceOverlay;
            _canvas.AddComponent<GraphicRaycaster>();
        }

        [TearDown]
        public void TearDown()
        {
            Object.DestroyImmediate(_canvas);
        }

        // ---- drop handler fires --------------------------------------------

        [UnityTest]
        public IEnumerator DragFromSourceToTargetInvokesDropHandler()
        {
            var src = MakeDraggable("drag_source");
            var dst = MakeDropTarget("drag_target");
            yield return null;

            yield return EngineInputDriver.Drag("drag_source", "drag_target", 50);

            Assert.IsTrue(dst.GetComponent<DropRecorder>().dropped,
                "IDropHandler.OnDrop must fire on the target");
        }

        [UnityTest]
        public IEnumerator DragInvokesBeginAndEndDragOnSource()
        {
            var src = MakeDraggable("drag_source");
            MakeDropTarget("drag_target");
            yield return null;

            yield return EngineInputDriver.Drag("drag_source", "drag_target", 50);

            var rec = src.GetComponent<DragRecorder>();
            Assert.AreEqual(1, rec.beginCount, "OnBeginDrag once");
            Assert.AreEqual(1, rec.endCount, "OnEndDrag once");
        }

        // ---- duration_ms → frame count -------------------------------------

        [UnityTest]
        public IEnumerator DragFrameCountMatchesDuration()
        {
            var src = MakeDraggable("drag_source");
            MakeDropTarget("drag_target");
            yield return null;

            const int durationMs = 80;
            int expected = EngineInputDriver.FrameCountFor(durationMs);
            Assert.AreEqual(5, expected, "80ms / 16ms-per-step = 5 frames");

            yield return EngineInputDriver.Drag("drag_source", "drag_target", durationMs);

            Assert.AreEqual(expected, src.GetComponent<DragRecorder>().dragCount,
                "OnDrag must fire once per frame for the duration");
        }

        // ---- error paths ----------------------------------------------------

        [Test]
        public void DragMissingSourceThrowsWidgetNotFound()
        {
            var ex = Assert.Throws<WireException>(() =>
            {
                var it = EngineInputDriver.Drag("no_such_source", "drag_target", 10);
                it.MoveNext(); // validation runs on first step
            });
            Assert.AreEqual(WireError.WidgetNotFound, ex.Code);
        }

        [Test]
        public void DragNonDraggableSourceThrowsWidgetNotInteractable()
        {
            // A plain Image has no IDragHandler / IBeginDragHandler.
            var src = MakeRect("plain_source");
            src.AddComponent<Image>();
            MakeDropTarget("drag_target");

            var ex = Assert.Throws<WireException>(() =>
            {
                var it = EngineInputDriver.Drag("plain_source", "drag_target", 10);
                it.MoveNext();
            });
            Assert.AreEqual(WireError.WidgetNotInteractable, ex.Code);
        }

        // ---- helpers -------------------------------------------------------

        GameObject MakeRect(string name)
        {
            var go = new GameObject(name);
            go.transform.SetParent(_canvas.transform, false);
            go.AddComponent<RectTransform>();
            return go;
        }

        GameObject MakeDraggable(string name)
        {
            var go = MakeRect(name);
            go.AddComponent<Image>();
            go.AddComponent<DragRecorder>();
            return go;
        }

        GameObject MakeDropTarget(string name)
        {
            var go = MakeRect(name);
            go.AddComponent<Image>();
            go.AddComponent<DropRecorder>();
            return go;
        }
    }

    // Test component: records the drag-lifecycle callbacks it receives.
    internal sealed class DragRecorder : MonoBehaviour,
        IBeginDragHandler, IDragHandler, IEndDragHandler
    {
        public int beginCount;
        public int dragCount;
        public int endCount;

        public void OnBeginDrag(PointerEventData e) => beginCount++;
        public void OnDrag(PointerEventData e) => dragCount++;
        public void OnEndDrag(PointerEventData e) => endCount++;
    }

    // Test component: records whether OnDrop fired.
    internal sealed class DropRecorder : MonoBehaviour, IDropHandler
    {
        public bool dropped;

        public void OnDrop(PointerEventData e) => dropped = true;
    }
}
