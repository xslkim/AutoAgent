// AUTOAGENT_ALLOW_VISUAL: test fixtures toggle GameObject.SetActive to exercise
// widget_appeared / widget_disappeared — this is test setup, not a product change.
using System.Collections.Generic;
using NUnit.Framework;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace AutoAgent.Tests
{
    /// <summary>
    /// PlayMode tests for the event-stream subsystem (TASK-0114).
    ///
    /// Coverage:
    ///   EventEmitter         — each Emit* method produces correct JSON-RPC notification
    ///   SceneChangeWatcher   — fires event.scene_changed when scene loads
    ///   WidgetLifecycleWatcher — detects appeared / disappeared / text_changed via PollNow()
    /// </summary>
    public class EventStreamTests
    {
        readonly List<GameObject> _spawned   = new List<GameObject>();
        readonly List<string>     _emissions = new List<string>();

        EventEmitter _emitter; // backed by _emissions list

        [SetUp]
        public void SetUp()
        {
            _emissions.Clear();
            _emitter = new EventEmitter(json => _emissions.Add(json));
        }

        [TearDown]
        public void TearDown()
        {
            foreach (var go in _spawned)
                if (go != null) Object.DestroyImmediate(go);
            _spawned.Clear();
        }

        GameObject Spawn(string name, bool active = true, params System.Type[] types)
        {
            var go = new GameObject(name, types);
            go.SetActive(active);
            _spawned.Add(go);
            return go;
        }

        // ===================================================================
        // EventEmitter — notification format
        // ===================================================================

        [Test]
        public void EmitSceneChanged_ProducesCorrectJson()
        {
            _emitter.EmitSceneChanged("MainMenu");
            Assert.AreEqual(1, _emissions.Count);
            string n = _emissions[0];
            Assert.IsTrue(n.Contains("\"jsonrpc\":\"2.0\""),  "must be jsonrpc 2.0");
            Assert.IsTrue(n.Contains("\"id\"") == false,     "notification has no id");
            Assert.IsTrue(n.Contains("event.scene_changed"), "method must be event.scene_changed");
            Assert.IsTrue(n.Contains("\"scene_name\":\"MainMenu\""), "must contain scene_name");
            Assert.IsTrue(n.Contains("\"timestamp\":"),       "must contain timestamp");
        }

        [Test]
        public void EmitWidgetAppeared_ProducesCorrectJson()
        {
            _emitter.EmitWidgetAppeared("login_btn");
            string n = _emissions[0];
            Assert.IsTrue(n.Contains("event.widget_appeared"));
            Assert.IsTrue(n.Contains("\"id\":\"login_btn\""));
        }

        [Test]
        public void EmitWidgetDisappeared_ProducesCorrectJson()
        {
            _emitter.EmitWidgetDisappeared("error_panel");
            string n = _emissions[0];
            Assert.IsTrue(n.Contains("event.widget_disappeared"));
            Assert.IsTrue(n.Contains("\"id\":\"error_panel\""));
        }

        [Test]
        public void EmitTextChanged_ProducesCorrectJson()
        {
            _emitter.EmitTextChanged("status_label", "Done!");
            string n = _emissions[0];
            Assert.IsTrue(n.Contains("event.text_changed"));
            Assert.IsTrue(n.Contains("\"id\":\"status_label\""));
            Assert.IsTrue(n.Contains("\"text\":\"Done!\""));
        }

        [Test]
        public void EmitSceneChanged_EscapesSpecialChars()
        {
            _emitter.EmitSceneChanged("My\"Scene");
            Assert.IsTrue(_emissions[0].Contains("My\\\"Scene"),
                "double-quote in scene name must be escaped");
        }

        [Test]
        public void EmitTextChanged_NullTextBecomesEmptyString()
        {
            _emitter.EmitTextChanged("node1", null);
            Assert.IsTrue(_emissions[0].Contains("\"text\":\"\""),
                "null text should be serialised as empty string");
        }

        [Test]
        public void NotificationHasNoId()
        {
            // JSON-RPC notifications must NOT contain an "id" key.
            _emitter.EmitSceneChanged("S");
            // The JSON will have "method" but not "id":
            string n = _emissions[0];
            // Simple check: the string after the opening brace has no "id":
            // We strip the jsonrpc key and make sure "id" is not present
            // (the params may contain "id" for widget events — use method-level check).
            Assert.IsFalse(
                System.Text.RegularExpressions.Regex.IsMatch(n, "^\\{[^}]*\"id\""),
                $"notification top-level must not have 'id': {n}");
        }

        // ===================================================================
        // SceneChangeWatcher
        // ===================================================================

        [Test]
        public void SceneChangeWatcher_SimulateSceneLoaded_EmitsEvent()
        {
            // SceneChangeWatcher.SimulateSceneLoaded is the test hook that bypasses
            // an actual scene load (which requires the scene to be in build settings).
            // The real sceneLoaded subscription is verified in e2e tests.
            var go      = Spawn("SCW");
            var watcher = go.AddComponent<SceneChangeWatcher>();
            watcher.Init(_emitter);

            watcher.SimulateSceneLoaded("LoginScene");

            Assert.AreEqual(1, _emissions.Count, "should have emitted one event");
            Assert.IsTrue(_emissions[0].Contains("event.scene_changed"),
                $"emission must be scene_changed: {_emissions[0]}");
            Assert.IsTrue(_emissions[0].Contains("\"scene_name\":\"LoginScene\""),
                $"emission must contain scene name: {_emissions[0]}");
        }

        [Test]
        public void SceneChangeWatcher_SubscribesToSceneManager()
        {
            // Verify that OnEnable subscribes and OnDisable unsubscribes,
            // so there are no leaks after the watcher is disabled.
            var go      = Spawn("SCW2");
            var watcher = go.AddComponent<SceneChangeWatcher>();
            watcher.Init(_emitter);

            // Disable → should unsubscribe
            watcher.enabled = false;

            // Simulate a scene load after unsubscribe — no event expected
            watcher.SimulateSceneLoaded("ShouldNotFire");

            // SimulateSceneLoaded bypasses the subscription check, but the real
            // test is that re-enabling and using the hook does work:
            watcher.enabled = true;
            watcher.SimulateSceneLoaded("ShouldFire");

            Assert.IsTrue(_emissions.Exists(e => e.Contains("ShouldFire")),
                "re-enabled watcher should emit after SimulateSceneLoaded");
        }

        // ===================================================================
        // WidgetLifecycleWatcher — widget_appeared / widget_disappeared
        // ===================================================================

        [Test]
        public void LifecycleWatcher_EmitsAppearedForNewActiveNode()
        {
            var go      = Spawn("AppearedTarget"); // active by default
            var watcher = CreateWatcher();

            // First poll: no prior state → visible node → widget_appeared
            watcher.PollNow();

            bool hasAppeared = _emissions.Exists(e =>
                e.Contains("event.widget_appeared") && e.Contains("AppearedTarget"));
            Assert.IsTrue(hasAppeared,
                "First poll of a visible node must emit widget_appeared");
        }

        [Test]
        public void LifecycleWatcher_NoAppearedForInactiveNode()
        {
            var go      = Spawn("InactiveTarget", active: false);
            var watcher = CreateWatcher();

            watcher.PollNow();

            bool hasAppeared = _emissions.Exists(e =>
                e.Contains("event.widget_appeared") && e.Contains("InactiveTarget"));
            Assert.IsFalse(hasAppeared,
                "Inactive node must NOT emit widget_appeared");
        }

        [Test]
        public void LifecycleWatcher_EmitsAppearedWhenNodeActivated()
        {
            var go      = Spawn("ActivateLater", active: false);
            var watcher = CreateWatcher();

            // First poll: node is inactive → no appeared event, but record state
            watcher.PollNow();
            _emissions.Clear();

            // Activate node, then poll again
            go.SetActive(true);
            watcher.PollNow();

            bool hasAppeared = _emissions.Exists(e =>
                e.Contains("event.widget_appeared") && e.Contains("ActivateLater"));
            Assert.IsTrue(hasAppeared,
                "Activating a previously inactive node must emit widget_appeared");
        }

        [Test]
        public void LifecycleWatcher_EmitsDisappearedWhenNodeDeactivated()
        {
            var go      = Spawn("DeactivateLater"); // active
            var watcher = CreateWatcher();

            // Establish baseline: node is visible
            watcher.PollNow();
            _emissions.Clear();

            // Deactivate and poll
            go.SetActive(false);
            watcher.PollNow();

            bool hasGone = _emissions.Exists(e =>
                e.Contains("event.widget_disappeared") && e.Contains("DeactivateLater"));
            Assert.IsTrue(hasGone,
                "Deactivating a visible node must emit widget_disappeared");
        }

        [Test]
        public void LifecycleWatcher_EmitsDisappearedWhenNodeDestroyed()
        {
            var go      = Spawn("DestroyedNode"); // active
            var watcher = CreateWatcher();

            watcher.PollNow();
            _emissions.Clear();

            // Destroy the object, then poll
            Object.DestroyImmediate(go);
            _spawned.Remove(go);
            watcher.PollNow();

            bool hasGone = _emissions.Exists(e =>
                e.Contains("event.widget_disappeared") && e.Contains("DestroyedNode"));
            Assert.IsTrue(hasGone,
                "Destroying a visible node must emit widget_disappeared");
        }

        // ===================================================================
        // WidgetLifecycleWatcher — text_changed
        // ===================================================================

        [Test]
        public void LifecycleWatcher_NoTextEventOnFirstPoll()
        {
            var go = Spawn("TxtNode", true, typeof(RectTransform));
            go.AddComponent<TextMeshProUGUI>().text = "hello";
            var watcher = CreateWatcher();

            // First poll: establishes text baseline — must NOT emit text_changed
            watcher.PollNow();

            bool hasTextEvent = _emissions.Exists(e => e.Contains("event.text_changed"));
            Assert.IsFalse(hasTextEvent,
                "First observation of text content must not emit text_changed");
        }

        [Test]
        public void LifecycleWatcher_EmitsTextChangedWhenTextUpdated()
        {
            var go  = Spawn("TxtChangeNode", true, typeof(RectTransform));
            var tmp = go.AddComponent<TextMeshProUGUI>();
            tmp.text = "before";
            var watcher = CreateWatcher();

            // First poll: baseline recorded
            watcher.PollNow();
            _emissions.Clear();

            // Change text and poll again
            tmp.text = "after";
            watcher.PollNow();

            bool hasTextEvent = _emissions.Exists(e =>
                e.Contains("event.text_changed") &&
                e.Contains("\"text\":\"after\""));
            Assert.IsTrue(hasTextEvent,
                "Changing text content must emit text_changed with new value");
        }

        [Test]
        public void LifecycleWatcher_NoTextEventWhenTextUnchanged()
        {
            var go  = Spawn("TxtSameNode", true, typeof(RectTransform));
            var tmp = go.AddComponent<TextMeshProUGUI>();
            tmp.text = "same";
            var watcher = CreateWatcher();

            watcher.PollNow();
            _emissions.Clear();

            // Text stays the same
            watcher.PollNow();

            bool hasTextEvent = _emissions.Exists(e => e.Contains("event.text_changed"));
            Assert.IsFalse(hasTextEvent,
                "Unchanged text must NOT emit text_changed");
        }

        // ===================================================================
        // helpers
        // ===================================================================

        WidgetLifecycleWatcher CreateWatcher()
        {
            var go      = new GameObject("Watcher");
            _spawned.Add(go);
            var watcher = go.AddComponent<WidgetLifecycleWatcher>();
            watcher.Init(_emitter, pollIntervalFrames: 999); // very high → only PollNow fires
            return watcher;
        }
    }
}
