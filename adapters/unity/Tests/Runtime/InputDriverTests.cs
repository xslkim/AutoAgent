using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace AutoAgent.Tests
{
    /// <summary>
    /// PlayMode tests: verify EngineInputDriver actions execute without error.
    /// An EventSystem must be present (Unity adds one when you run PlayMode tests).
    /// </summary>
    public class InputDriverTests
    {
        GameObject _canvas;

        [SetUp]
        public void SetUp()
        {
            _canvas = new GameObject("TestCanvas");
            var c = _canvas.AddComponent<Canvas>();
            c.renderMode = RenderMode.ScreenSpaceOverlay;
            _canvas.AddComponent<GraphicRaycaster>();
        }

        [TearDown]
        public void TearDown()
        {
            Object.DestroyImmediate(_canvas);
        }

        // Click coverage moved to ClickTests (TASK-0105); send_text coverage
        // moved to SendTextTests (TASK-0106) — both now throw WireException
        // instead of returning a bool.

        // ---- scroll -------------------------------------------------------

        [UnityTest]
        public IEnumerator Scroll_ScrollRect_ChangesNormalizedPosition()
        {
            var go = MakeScrollRect("scroller");
            var sr = go.GetComponent<ScrollRect>();
            sr.normalizedPosition = new Vector2(0, 1f);

            yield return null;
            EngineInputDriver.Scroll("scroller", 0f, -0.1f);
            yield return null;

            Assert.Less(sr.normalizedPosition.y, 1f, "scroll rect should have moved");
        }

        // ---- helpers -------------------------------------------------------

        GameObject MakeScrollRect(string name)
        {
            var go = new GameObject(name);
            go.transform.SetParent(_canvas.transform, false);
            go.AddComponent<RectTransform>();
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
