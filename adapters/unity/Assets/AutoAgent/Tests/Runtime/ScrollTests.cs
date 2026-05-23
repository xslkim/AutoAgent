// AUTOAGENT_ALLOW_VISUAL: test fixtures set RectTransform size/position for test setup.
using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace AutoAgent.Tests
{
    /// <summary>
    /// PlayMode tests for EngineInputDriver.Scroll (TASK-0108).
    /// Scroll mutates the enclosing ScrollRect's normalizedPosition; throws
    /// a WireException for missing nodes or nodes with no ScrollRect.
    /// </summary>
    public class ScrollTests
    {
        GameObject _canvas;

        [SetUp]
        public void SetUp()
        {
            _canvas = new GameObject("ScrollTestCanvas");
            var c = _canvas.AddComponent<Canvas>();
            c.renderMode = RenderMode.ScreenSpaceOverlay;
            _canvas.AddComponent<GraphicRaycaster>();
        }

        [TearDown]
        public void TearDown()
        {
            Object.DestroyImmediate(_canvas);
        }

        // ---- happy path ----------------------------------------------------

        [UnityTest]
        public IEnumerator ScrollOnScrollRectChangesNormalizedPosition()
        {
            var go = MakeScrollRect("scroller");
            var sr = go.GetComponent<ScrollRect>();
            sr.normalizedPosition = new Vector2(0f, 1f);
            yield return null;

            EngineInputDriver.Scroll("scroller", 0f, -0.3f);
            yield return null;

            Assert.Less(sr.normalizedPosition.y, 1f, "scroll rect should have moved down");
        }

        [UnityTest]
        public IEnumerator ScrollResolvesScrollRectOnAncestor()
        {
            // Address the Content child — the ScrollRect lives on the parent.
            var scroller = MakeScrollRect("scroller_parent");
            var content = scroller.transform.Find("Content").gameObject;
            content.name = "scroll_content";
            var sr = scroller.GetComponent<ScrollRect>();
            sr.normalizedPosition = new Vector2(0f, 1f);
            yield return null;

            EngineInputDriver.Scroll("scroll_content", 0f, -0.2f);
            yield return null;

            Assert.Less(sr.normalizedPosition.y, 1f,
                "ScrollRect lookup must walk up to the parent");
        }

        [UnityTest]
        public IEnumerator ScrollFiresOnValueChanged()
        {
            bool fired = false;
            var go = MakeScrollRect("scroller");
            var sr = go.GetComponent<ScrollRect>();
            sr.normalizedPosition = new Vector2(0f, 1f);
            sr.onValueChanged.AddListener(_ => fired = true);
            yield return null;

            EngineInputDriver.Scroll("scroller", 0f, -0.2f);
            yield return null;

            Assert.IsTrue(fired, "ScrollRect.onValueChanged must fire on Scroll");
        }

        // ---- error paths ----------------------------------------------------

        [Test]
        public void ScrollWithoutScrollRectThrowsWidgetNotInteractable()
        {
            var go = MakeRect("PlainImageNode");
            go.AddComponent<Image>();

            var ex = Assert.Throws<WireException>(
                () => EngineInputDriver.Scroll("PlainImageNode", 0f, -0.1f));
            Assert.AreEqual(WireError.WidgetNotInteractable, ex.Code);
        }

        [Test]
        public void ScrollMissingIdThrowsWidgetNotFound()
        {
            var ex = Assert.Throws<WireException>(
                () => EngineInputDriver.Scroll("no_such_node", 0f, -0.1f));
            Assert.AreEqual(WireError.WidgetNotFound, ex.Code);
        }

        // ---- helpers -------------------------------------------------------

        GameObject MakeRect(string name)
        {
            var go = new GameObject(name);
            go.transform.SetParent(_canvas.transform, false);
            go.AddComponent<RectTransform>();
            return go;
        }

        GameObject MakeScrollRect(string name)
        {
            var go = MakeRect(name);
            var sr = go.AddComponent<ScrollRect>();

            var content = new GameObject("Content");
            content.transform.SetParent(go.transform, false);
            var contentRt = content.AddComponent<RectTransform>();
            contentRt.sizeDelta = new Vector2(0, 1000);
            sr.content = contentRt;
            return go;
        }
    }
}
