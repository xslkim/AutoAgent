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

        // ---- helpers -------------------------------------------------------

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
