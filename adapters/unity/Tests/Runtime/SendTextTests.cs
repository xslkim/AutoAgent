using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UI;
using TMPro;

namespace AutoAgent.Tests
{
    /// <summary>
    /// PlayMode tests for EngineInputDriver.SendText (TASK-0106).
    /// SendText writes a TMP_InputField / legacy InputField, honours
    /// clear_first, fires onValueChanged + onEndEdit, and throws a
    /// WireException for missing / non-input nodes.
    /// </summary>
    public class SendTextTests
    {
        GameObject _canvas;

        [SetUp]
        public void SetUp()
        {
            _canvas = new GameObject("SendTextCanvas");
            var c = _canvas.AddComponent<Canvas>();
            c.renderMode = RenderMode.ScreenSpaceOverlay;
            _canvas.AddComponent<GraphicRaycaster>();
        }

        [TearDown]
        public void TearDown()
        {
            Object.DestroyImmediate(_canvas);
        }

        // ---- TMP_InputField: set + onValueChanged --------------------------

        [UnityTest]
        public IEnumerator SendTextSetsTmpInputFieldAndFiresOnValueChanged()
        {
            string changedValue = null;
            var go = MakeTmpInputField("account");
            go.GetComponent<TMP_InputField>().onValueChanged.AddListener(v => changedValue = v);
            yield return null;

            EngineInputDriver.SendText("account", "hello@test.com");
            yield return null;

            Assert.AreEqual("hello@test.com", go.GetComponent<TMP_InputField>().text);
            Assert.AreEqual("hello@test.com", changedValue, "onValueChanged must fire with the new value");
        }

        [UnityTest]
        public IEnumerator SendTextFiresOnEndEdit()
        {
            string submitted = null;
            var go = MakeTmpInputField("field");
            go.GetComponent<TMP_InputField>().onEndEdit.AddListener(v => submitted = v);
            yield return null;

            EngineInputDriver.SendText("field", "done");
            yield return null;

            Assert.AreEqual("done", submitted, "onEndEdit must fire");
        }

        // ---- clear_first ----------------------------------------------------

        [UnityTest]
        public IEnumerator ClearFirstTrueReplacesOldValue()
        {
            var go = MakeTmpInputField("field");
            var tmp = go.GetComponent<TMP_InputField>();
            tmp.text = "stale value";
            yield return null;

            EngineInputDriver.SendText("field", "fresh", clearFirst: true);
            yield return null;

            Assert.AreEqual("fresh", tmp.text, "clear_first=true must drop the old value");
        }

        [UnityTest]
        public IEnumerator ClearFirstFalseAppendsToOldValue()
        {
            var go = MakeTmpInputField("field");
            var tmp = go.GetComponent<TMP_InputField>();
            tmp.text = "abc";
            yield return null;

            EngineInputDriver.SendText("field", "def", clearFirst: false);
            yield return null;

            Assert.AreEqual("abcdef", tmp.text, "clear_first=false must append");
        }

        // ---- legacy InputField ---------------------------------------------

        [UnityTest]
        public IEnumerator SendTextSetsLegacyInputField()
        {
            string changedValue = null;
            var go = MakeLegacyInputField("legacy");
            go.GetComponent<InputField>().onValueChanged.AddListener(v => changedValue = v);
            yield return null;

            EngineInputDriver.SendText("legacy", "typed");
            yield return null;

            Assert.AreEqual("typed", go.GetComponent<InputField>().text);
            Assert.AreEqual("typed", changedValue);
        }

        // ---- error paths ----------------------------------------------------

        [Test]
        public void SendTextToNonInputThrowsWidgetNotInteractable()
        {
            var go = MakeRect("PlainImage");
            go.AddComponent<Image>();

            var ex = Assert.Throws<WireException>(
                () => EngineInputDriver.SendText("PlainImage", "x"));
            Assert.AreEqual(WireError.WidgetNotInteractable, ex.Code);
        }

        [Test]
        public void SendTextToMissingIdThrowsWidgetNotFound()
        {
            var ex = Assert.Throws<WireException>(
                () => EngineInputDriver.SendText("no_such_field", "x"));
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

        GameObject MakeTmpInputField(string name)
        {
            var go = MakeRect(name);
            go.AddComponent<Image>();
            var inf = go.AddComponent<TMP_InputField>();

            var textArea = new GameObject("Text Area");
            textArea.transform.SetParent(go.transform, false);
            textArea.AddComponent<RectTransform>();
            inf.textComponent = textArea.AddComponent<TextMeshProUGUI>();
            return go;
        }

        GameObject MakeLegacyInputField(string name)
        {
            var go = MakeRect(name);
            go.AddComponent<Image>();
            var inf = go.AddComponent<InputField>();

            var textChild = new GameObject("Text");
            textChild.transform.SetParent(go.transform, false);
            textChild.AddComponent<RectTransform>();
            inf.textComponent = textChild.AddComponent<Text>();
            return go;
        }
    }
}
