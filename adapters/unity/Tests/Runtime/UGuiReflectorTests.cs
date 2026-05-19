using System.Collections;
using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UI;
using TMPro;

namespace AutoAgent.Tests
{
    /// <summary>
    /// PlayMode tests: verify UGuiReflector dumps the active scene correctly.
    /// Requires an EventSystem in the scene (Unity Test Runner provides one).
    /// </summary>
    public class UGuiReflectorTests
    {
        GameObject _canvas;

        [SetUp]
        public void SetUp()
        {
            _canvas = new GameObject("TestCanvas");
            var canvas = _canvas.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            _canvas.AddComponent<CanvasScaler>();
            _canvas.AddComponent<GraphicRaycaster>();
        }

        [TearDown]
        public void TearDown()
        {
            Object.DestroyImmediate(_canvas);
        }

        // ---- parent/children consistency -----------------------------------

        [UnityTest]
        public IEnumerator ParentChildRelationshipIsConsistent()
        {
            // Build: Canvas > Panel > Button
            var panel = MakeRect("Panel", _canvas.transform);
            var button = MakeRect("Button", panel.transform);
            button.gameObject.AddComponent<Image>();
            button.gameObject.AddComponent<Button>();

            yield return null; // let Unity settle

            var nodes = UGuiReflector.DumpActiveScene();
            var nodeMap = BuildMap(nodes);

            Assert.IsTrue(nodeMap.ContainsKey("TestCanvas"), "root missing");
            Assert.IsTrue(nodeMap.ContainsKey("Panel"), "Panel missing");
            Assert.IsTrue(nodeMap.ContainsKey("Button"), "Button missing");

            var canvasNode = nodeMap["TestCanvas"];
            Assert.Contains("Panel", canvasNode.ChildrenIds);

            var panelNode = nodeMap["Panel"];
            Assert.AreEqual("TestCanvas", panelNode.ParentId);
            Assert.Contains("Button", panelNode.ChildrenIds);

            var btnNode = nodeMap["Button"];
            Assert.AreEqual("Panel", btnNode.ParentId);
            Assert.AreEqual(0, btnNode.ChildrenIds.Count);
        }

        // ---- StableIdComponent (pinned) ------------------------------------

        [UnityTest]
        public IEnumerator PinnedIdOverridesGameObjectName()
        {
            var go = MakeRect("RawName", _canvas.transform).gameObject;
            var sid = go.AddComponent<StableIdComponent>();
            sid.pinnedId = "pinned_name";

            yield return null;

            var nodes = UGuiReflector.DumpActiveScene();
            var nodeMap = BuildMap(nodes);

            Assert.IsTrue(nodeMap.ContainsKey("pinned_name"), "pinned id missing");
            Assert.IsFalse(nodeMap.ContainsKey("RawName"), "raw name should be replaced");
            Assert.AreEqual("pinned", nodeMap["pinned_name"].StableIdSource);
        }

        // ---- visual fields -------------------------------------------------

        [UnityTest]
        public IEnumerator VisibleFlagReflectsGameObjectActive()
        {
            var rt = MakeRect("VisTest", _canvas.transform);
            rt.gameObject.SetActive(false);

            yield return null;

            var nodes = UGuiReflector.DumpActiveScene();
            var map = BuildMap(nodes);
            Assert.IsTrue(map.ContainsKey("VisTest"));
            Assert.IsFalse(map["VisTest"].Visual.Visible);
        }

        // ---- type resolution -----------------------------------------------

        [UnityTest]
        public IEnumerator ButtonNodeHasCorrectType()
        {
            var go = MakeRect("Btn", _canvas.transform).gameObject;
            go.AddComponent<Image>();
            go.AddComponent<Button>();

            yield return null;

            var nodes = UGuiReflector.DumpActiveScene();
            var map = BuildMap(nodes);
            Assert.AreEqual("Button", map["Btn"].Type);
            Assert.AreEqual("UnityEngine.UI.Button", map["Btn"].EngineType);
        }

        // ---- TASK-0100: complete field coverage ----------------------------

        [UnityTest]
        public IEnumerator FullyReflectedButtonHasAllVerificationFields()
        {
            // Button + Image with a sprite — the canonical interactive widget.
            var go = MakeRect("LoginBtn", _canvas.transform).gameObject;
            var img = go.AddComponent<Image>();
            img.color = new Color(0.2f, 0.4f, 0.8f, 1f);
            img.sprite = MakeSprite();
            go.AddComponent<Button>();

            yield return null;

            var node = BuildMap(UGuiReflector.DumpActiveScene())["LoginBtn"];

            // The six fields TASK-0100 verification requires to be non-empty.
            Assert.IsNotNull(node.Visual, "visual missing");
            Assert.IsTrue(node.Visual.Visible, "visible should be true");
            Assert.IsTrue(node.Visual.Alpha.HasValue, "alpha must be populated");
            Assert.IsNotNull(node.Visual.Color, "color must be populated");
            Assert.IsNotNull(node.Visual.SpriteRef, "sprite_ref must be populated");

            Assert.IsNotNull(node.Behavior, "behavior missing");
            Assert.IsTrue(node.Behavior.Interactable.HasValue, "interactable must be populated");
            Assert.IsNotEmpty(node.Behavior.EventHandlers, "event_handlers must be non-empty");
            Assert.Contains("onClick", node.Behavior.EventHandlers);
        }

        [UnityTest]
        public IEnumerator NewVisualFieldsArePopulated()
        {
            var go = MakeRect("VisNode", _canvas.transform).gameObject;
            go.AddComponent<Image>();

            yield return null;

            var v = BuildMap(UGuiReflector.DumpActiveScene())["VisNode"].Visual;
            Assert.IsNotNull(v.Anchor, "anchor must be populated");
            Assert.AreEqual(2, v.Anchor.Length);
            Assert.IsTrue(v.ZOrder.HasValue, "z_order must be populated");
        }

        [UnityTest]
        public IEnumerator AlphaFallsBackToGraphicColorAlpha()
        {
            // No CanvasGroup → alpha comes from the Graphic's color alpha.
            var go = MakeRect("HalfAlpha", _canvas.transform).gameObject;
            var img = go.AddComponent<Image>();
            img.color = new Color(1f, 1f, 1f, 0.5f);

            yield return null;

            var v = BuildMap(UGuiReflector.DumpActiveScene())["HalfAlpha"].Visual;
            Assert.IsTrue(v.Alpha.HasValue);
            Assert.AreEqual(0.5f, v.Alpha.Value, 0.02f);
        }

        [UnityTest]
        public IEnumerator InputFieldExposesEditEventHandlers()
        {
            var go = MakeRect("Field", _canvas.transform).gameObject;
            go.AddComponent<Image>();
            go.AddComponent<InputField>();

            yield return null;

            var b = BuildMap(UGuiReflector.DumpActiveScene())["Field"].Behavior;
            Assert.Contains("onValueChanged", b.EventHandlers);
            Assert.Contains("onEndEdit", b.EventHandlers);
        }

        [UnityTest]
        public IEnumerator InteractiveWidgetGoesIntoAttachedComponents()
        {
            var go = MakeRect("ToggleNode", _canvas.transform).gameObject;
            go.AddComponent<Image>();
            go.AddComponent<Toggle>();

            yield return null;

            var b = BuildMap(UGuiReflector.DumpActiveScene())["ToggleNode"].Behavior;
            Assert.Contains("Toggle", b.AttachedComponents);
        }

        [UnityTest]
        public IEnumerator BareImageNodeHasEmptyAttachedComponents()
        {
            // A fixture node with no interactivity — attached_components stays empty
            // (TASK-0131 precondition; AI populates it later in TASK-0132).
            var go = MakeRect("PlainImage", _canvas.transform).gameObject;
            go.AddComponent<Image>();

            yield return null;

            var b = BuildMap(UGuiReflector.DumpActiveScene())["PlainImage"].Behavior;
            Assert.IsEmpty(b.AttachedComponents);
        }

        // ---- helpers -------------------------------------------------------

        static Sprite MakeSprite()
        {
            var tex = new Texture2D(4, 4);
            return Sprite.Create(tex, new Rect(0, 0, 4, 4), new Vector2(0.5f, 0.5f));
        }

        static RectTransform MakeRect(string name, Transform parent)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            return go.AddComponent<RectTransform>();
        }

        static Dictionary<string, NodeData> BuildMap(List<NodeData> nodes)
        {
            var d = new Dictionary<string, NodeData>();
            foreach (var n in nodes) d[n.Id] = n;
            return d;
        }
    }
}
