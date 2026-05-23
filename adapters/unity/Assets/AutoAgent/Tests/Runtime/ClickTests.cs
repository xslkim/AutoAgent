using System.Collections;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace AutoAgent.Tests
{
    /// <summary>
    /// PlayMode tests for EngineInputDriver.Click (TASK-0105).
    /// Click fires a full PointerDown → Up → Click sequence and throws a
    /// WireException for missing / non-interactable nodes.
    /// </summary>
    public class ClickTests
    {
        GameObject _canvas;
        GameObject _eventSystem;

        [SetUp]
        public void SetUp()
        {
            _canvas = new GameObject("ClickTestCanvas");
            var c = _canvas.AddComponent<Canvas>();
            c.renderMode = RenderMode.ScreenSpaceOverlay;
            _canvas.AddComponent<GraphicRaycaster>();
            // A bare EventSystem so PointerEventData has a system to reference.
            _eventSystem = new GameObject("ClickTestEventSystem", typeof(EventSystem));
        }

        [TearDown]
        public void TearDown()
        {
            Object.DestroyImmediate(_canvas);
            Object.DestroyImmediate(_eventSystem);
        }

        // ---- Button.onClick ------------------------------------------------

        [UnityTest]
        public IEnumerator ClickButtonInvokesOnClick()
        {
            bool clicked = false;
            var go = MakeRect("ClickBtn");
            go.AddComponent<Image>();
            go.AddComponent<Button>().onClick.AddListener(() => clicked = true);
            yield return null;

            EngineInputDriver.Click("ClickBtn");
            yield return null;

            Assert.IsTrue(clicked, "Button.onClick must fire on Click");
        }

        // ---- Toggle.onValueChanged -----------------------------------------

        [UnityTest]
        public IEnumerator ClickToggleInvokesOnValueChanged()
        {
            bool changed = false;
            var go = MakeRect("ClickToggle");
            go.AddComponent<Image>();
            var toggle = go.AddComponent<Toggle>();
            toggle.isOn = false;
            toggle.onValueChanged.AddListener(_ => changed = true);
            yield return null;

            EngineInputDriver.Click("ClickToggle");
            yield return null;

            Assert.IsTrue(changed, "Toggle.onValueChanged must fire on Click");
            Assert.IsTrue(toggle.isOn, "Toggle should have flipped on");
        }

        // ---- non-interactable → -32002 -------------------------------------

        [Test]
        public void ClickNonInteractableNodeThrowsWidgetNotInteractable()
        {
            // A plain Image node has no Selectable / pointer handler.
            var go = MakeRect("PlainImageNode");
            go.AddComponent<Image>();

            var ex = Assert.Throws<WireException>(
                () => EngineInputDriver.Click("PlainImageNode"));
            Assert.AreEqual(WireError.WidgetNotInteractable, ex.Code);
        }

        // ---- missing id → -32001 -------------------------------------------

        [Test]
        public void ClickMissingIdThrowsWidgetNotFound()
        {
            var ex = Assert.Throws<WireException>(
                () => EngineInputDriver.Click("no_such_node"));
            Assert.AreEqual(WireError.WidgetNotFound, ex.Code);
        }

        // ---- pinned id resolution ------------------------------------------

        [UnityTest]
        public IEnumerator ClickResolvesPinnedId()
        {
            bool clicked = false;
            var go = MakeRect("raw_object_name");
            go.AddComponent<Image>();
            go.AddComponent<Button>().onClick.AddListener(() => clicked = true);
            go.AddComponent<StableIdComponent>().pinnedId = "login_button";
            yield return null;

            EngineInputDriver.Click("login_button");
            yield return null;

            Assert.IsTrue(clicked, "Click must resolve a pinned id");
        }

        // ---- helpers -------------------------------------------------------

        GameObject MakeRect(string name)
        {
            var go = new GameObject(name);
            go.transform.SetParent(_canvas.transform, false);
            go.AddComponent<RectTransform>();
            return go;
        }
    }
}
