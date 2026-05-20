using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.TestTools;
using UnityEngine.UI;
using TMPro;

namespace AutoAgent.Tests
{
    /// <summary>
    /// PlayMode tests for EngineInputDriver.KeyPress (TASK-0109).
    /// Enter → ISubmitHandler (InputField.onSubmit / Button.onClick),
    /// Tab → focus the next Selectable.
    /// </summary>
    public class KeyPressTests
    {
        GameObject _canvas;
        GameObject _eventSystem;

        [SetUp]
        public void SetUp()
        {
            _canvas = new GameObject("KeyPressCanvas");
            var c = _canvas.AddComponent<Canvas>();
            c.renderMode = RenderMode.ScreenSpaceOverlay;
            _canvas.AddComponent<GraphicRaycaster>();
            _eventSystem = new GameObject("KeyPressEventSystem", typeof(EventSystem));
        }

        [TearDown]
        public void TearDown()
        {
            Object.DestroyImmediate(_canvas);
            Object.DestroyImmediate(_eventSystem);
        }

        // ---- Enter → ISubmitHandler ----------------------------------------

        [UnityTest]
        public IEnumerator EnterFiresInputFieldOnSubmit()
        {
            string submitted = null;
            var go = MakeTmpInputField("field");
            go.GetComponent<TMP_InputField>().onSubmit.AddListener(v => submitted = v);
            yield return null;

            EngineInputDriver.KeyPress("field", "Enter");
            yield return null;

            Assert.IsNotNull(submitted, "TMP_InputField.onSubmit must fire on Enter");
        }

        [UnityTest]
        public IEnumerator EnterFiresButtonOnClickViaSubmit()
        {
            bool clicked = false;
            var go = MakeButton("btn");
            go.GetComponent<Button>().onClick.AddListener(() => clicked = true);
            yield return null;

            EngineInputDriver.KeyPress("btn", "Enter");
            yield return null;

            Assert.IsTrue(clicked, "Button.onClick must fire on Enter (via ISubmitHandler)");
        }

        // ---- Tab → focus next Selectable -----------------------------------

        [UnityTest]
        public IEnumerator TabFocusesNextSelectable()
        {
            var a = MakeButton("btn_a");
            var b = MakeButton("btn_b");
            EventSystem.current.SetSelectedGameObject(a);
            yield return null;
            Assert.AreEqual(a, EventSystem.current.currentSelectedGameObject,
                "pre-condition: A is selected");

            EngineInputDriver.KeyPress("btn_a", "Tab");
            yield return null;

            Assert.AreNotEqual(a, EventSystem.current.currentSelectedGameObject,
                "Tab must move focus away from A");
            Assert.AreEqual(b, EventSystem.current.currentSelectedGameObject,
                "Tab from A must select B (the next Selectable)");
        }

        [UnityTest]
        public IEnumerator ShiftTabFocusesPreviousSelectable()
        {
            var a = MakeButton("btn_a");
            var b = MakeButton("btn_b");
            EventSystem.current.SetSelectedGameObject(b);
            yield return null;

            EngineInputDriver.KeyPress("btn_b", "Shift+Tab");
            yield return null;

            Assert.AreEqual(a, EventSystem.current.currentSelectedGameObject,
                "Shift+Tab from B must move focus back to A");
        }

        // ---- error paths ----------------------------------------------------

        [Test]
        public void EnterOnNonSubmittableThrowsWidgetNotInteractable()
        {
            // A plain Image has no ISubmitHandler.
            var go = MakeRect("PlainImage");
            go.AddComponent<Image>();

            var ex = Assert.Throws<WireException>(
                () => EngineInputDriver.KeyPress("PlainImage", "Enter"));
            Assert.AreEqual(WireError.WidgetNotInteractable, ex.Code);
        }

        [Test]
        public void TabOnNonSelectableThrowsWidgetNotInteractable()
        {
            var go = MakeRect("PlainImage");
            go.AddComponent<Image>();

            var ex = Assert.Throws<WireException>(
                () => EngineInputDriver.KeyPress("PlainImage", "Tab"));
            Assert.AreEqual(WireError.WidgetNotInteractable, ex.Code);
        }

        [Test]
        public void KeyPressMissingIdThrowsWidgetNotFound()
        {
            var ex = Assert.Throws<WireException>(
                () => EngineInputDriver.KeyPress("no_such_node", "Enter"));
            Assert.AreEqual(WireError.WidgetNotFound, ex.Code);
        }

        [Test]
        public void UnsupportedKeyThrowsInvalidParams()
        {
            var go = MakeButton("btn");
            var ex = Assert.Throws<WireException>(
                () => EngineInputDriver.KeyPress("btn", "F12"));
            Assert.AreEqual(WireError.InvalidParams, ex.Code);
        }

        // ---- helpers -------------------------------------------------------

        GameObject MakeRect(string name)
        {
            var go = new GameObject(name);
            go.transform.SetParent(_canvas.transform, false);
            go.AddComponent<RectTransform>();
            return go;
        }

        GameObject MakeButton(string name)
        {
            var go = MakeRect(name);
            go.AddComponent<Image>();
            go.AddComponent<Button>();
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
    }
}
