using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UI;
using TMPro;

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

        // ---- click --------------------------------------------------------

        [UnityTest]
        public IEnumerator Click_ButtonById_InvokesOnClick()
        {
            bool clicked = false;
            var go = MakeButton("btn_login");
            go.GetComponent<Button>().onClick.AddListener(() => clicked = true);

            yield return null;
            EngineInputDriver.Click("btn_login");
            yield return null;

            Assert.IsTrue(clicked, "onClick should have been invoked");
        }

        [UnityTest]
        public IEnumerator Click_NonExistentId_ReturnsFalse()
        {
            yield return null;
            bool result = EngineInputDriver.Click("id_does_not_exist");
            Assert.IsFalse(result);
        }

        // ---- send_text ----------------------------------------------------

        [UnityTest]
        public IEnumerator SendText_TmpInputField_SetsText()
        {
            var go = MakeTmpInputField("input_account");

            yield return null;
            EngineInputDriver.SendText("input_account", "hello@test.com");
            yield return null;

            Assert.AreEqual("hello@test.com", go.GetComponent<TMP_InputField>().text);
        }

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

        GameObject MakeButton(string name)
        {
            var go = new GameObject(name);
            go.transform.SetParent(_canvas.transform, false);
            go.AddComponent<RectTransform>();
            go.AddComponent<Image>();
            go.AddComponent<Button>();
            return go;
        }

        GameObject MakeTmpInputField(string name)
        {
            // TMP_InputField requires a child Text area
            var go = new GameObject(name);
            go.transform.SetParent(_canvas.transform, false);
            go.AddComponent<RectTransform>();
            go.AddComponent<Image>();
            var inf = go.AddComponent<TMP_InputField>();

            var textArea = new GameObject("Text Area");
            textArea.transform.SetParent(go.transform, false);
            textArea.AddComponent<RectTransform>();
            var tmp = textArea.AddComponent<TextMeshProUGUI>();
            inf.textComponent = tmp;
            return go;
        }

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
