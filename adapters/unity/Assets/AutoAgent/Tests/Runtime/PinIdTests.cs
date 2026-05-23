using System.Collections.Generic;
using System.IO;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace AutoAgent.Tests
{
    /// <summary>
    /// PlayMode tests for the pin_id and list_orphan_ids wire methods (TASK-0116).
    ///
    /// pin_id:
    ///   • Attaches / updates StableIdComponent.pinnedId on the target widget.
    ///   • The next dump_tree call returns stable_id_source = "pinned".
    ///   • Returns -32602 on missing params, -32001 on unknown widget.
    ///
    /// list_orphan_ids:
    ///   • Returns ids that were saved to the tracker but are absent from the scene.
    ///   • Does NOT return ids of nodes still present.
    ///   • Returns [] when no previous scan exists or tracker is null.
    /// </summary>
    public class PinIdTests
    {
        readonly List<GameObject> _created = new List<GameObject>();

        [TearDown]
        public void TearDown()
        {
            foreach (var go in _created)
                if (go != null) Object.DestroyImmediate(go);
            _created.Clear();
        }

        // Creates a root UI widget and registers it for cleanup.
        GameObject MakeWidget(string name)
        {
            var go = new GameObject(name);
            go.AddComponent<RectTransform>();
            _created.Add(go);
            return go;
        }

        // Returns the current wire id of a widget via IdAllocator (same logic as dump_tree).
        static string FindNodeId(GameObject go)
        {
            var roots = SceneManager.GetActiveScene().GetRootGameObjects();
            var alloc = IdAllocator.Allocate(roots);
            return alloc.IdOf(go.transform);
        }

        // ===================================================================
        // pin_id — happy path
        // ===================================================================

        [Test]
        public void PinIdSetsStableIdComponentPinnedId()
        {
            var go = MakeWidget("PinTarget_SetComp");

            string currentId = FindNodeId(go);
            Assert.IsNotNull(currentId, "widget must appear in dump");

            string result = PinIdHandler.HandlePinId(1,
                $"{{\"id\":\"{currentId}\",\"pinned_id\":\"my_button\"}}");

            Assert.IsTrue(result.Contains("\"result\":"), $"unexpected: {result}");

            var sid = go.GetComponent<StableIdComponent>();
            Assert.IsNotNull(sid, "StableIdComponent must have been added");
            Assert.AreEqual("my_button", sid.pinnedId);
        }

        [Test]
        public void PinIdMakesNextDumpReturnPinnedSource()
        {
            var go = MakeWidget("PinTarget_Source");

            string currentId = FindNodeId(go);
            Assert.IsNotNull(currentId);

            PinIdHandler.HandlePinId(1,
                $"{{\"id\":\"{currentId}\",\"pinned_id\":\"pinned_node\"}}");

            // After pinning, a fresh dump must reflect stable_id_source = "pinned".
            var nodes = UGuiReflector.DumpActiveScene();
            NodeData pinned = nodes.Find(n => n.Id == "pinned_node");
            Assert.IsNotNull(pinned,
                "node must appear under its new pinned id after pin_id");
            Assert.AreEqual("pinned", pinned.StableIdSource,
                "stable_id_source must be 'pinned' after pin_id");
        }

        [Test]
        public void PinIdOverwritesExistingPin()
        {
            var go = MakeWidget("PinTarget_Overwrite");
            // Pre-attach with an old pin; FindById falls back to StableIdComponent.
            var sid = go.AddComponent<StableIdComponent>();
            sid.pinnedId = "old_pin";

            string result = PinIdHandler.HandlePinId(1,
                "{\"id\":\"old_pin\",\"pinned_id\":\"new_pin\"}");

            Assert.IsTrue(result.Contains("\"result\":"), $"unexpected: {result}");
            Assert.AreEqual("new_pin",
                go.GetComponent<StableIdComponent>().pinnedId,
                "pinnedId must be updated to 'new_pin'");
        }

        [Test]
        public void PinIdNodeIsResolvableByNewPinAfterPinning()
        {
            var go = MakeWidget("PinTarget_Resolve");
            string currentId = FindNodeId(go);
            Assert.IsNotNull(currentId);

            PinIdHandler.HandlePinId(1,
                $"{{\"id\":\"{currentId}\",\"pinned_id\":\"resolved_pin\"}}");

            // FindById must now return the same GameObject when called with the new pin.
            var found = EngineInputDriver.FindById("resolved_pin");
            Assert.IsNotNull(found, "FindById must resolve the new pinned id");
            Assert.AreEqual(go.GetInstanceID(), found.GetInstanceID(),
                "FindById must return the original widget");
        }

        // ===================================================================
        // pin_id — validation errors
        // ===================================================================

        [Test]
        public void PinIdMissingIdParamReturnsInvalidParams()
        {
            string result = PinIdHandler.HandlePinId(1, "{\"pinned_id\":\"foo\"}");
            Assert.IsTrue(result.Contains("\"code\":-32602"), $"unexpected: {result}");
        }

        [Test]
        public void PinIdMissingPinnedIdParamReturnsInvalidParams()
        {
            string result = PinIdHandler.HandlePinId(1, "{\"id\":\"some_id\"}");
            Assert.IsTrue(result.Contains("\"code\":-32602"), $"unexpected: {result}");
        }

        [Test]
        public void PinIdUnknownWidgetReturnsWidgetNotFound()
        {
            string result = PinIdHandler.HandlePinId(1,
                "{\"id\":\"definitely_not_a_real_node\",\"pinned_id\":\"p\"}");
            Assert.IsTrue(result.Contains("\"code\":-32001"), $"unexpected: {result}");
        }

        // ===================================================================
        // list_orphan_ids
        // ===================================================================

        [Test]
        public void ListOrphanIdsNoPreviousScanReturnsEmptyArray()
        {
            using var tmp = new TempTrackerScope();
            // No Save() call → tracker has no previous scan.
            string result = PinIdHandler.HandleListOrphanIds(1, tmp.Tracker);

            Assert.IsTrue(result.Contains("\"result\":"), $"unexpected: {result}");
            Assert.IsTrue(result.Contains("[]"),
                $"no previous scan → orphans must be []: {result}");
        }

        [Test]
        public void ListOrphanIdsReturnsMissingIds()
        {
            using var tmp = new TempTrackerScope();
            // Simulate a previous scan with two ids that don't exist in the scene.
            tmp.Tracker.Save(new[] { "gone_widget_1", "gone_widget_2" });

            string result = PinIdHandler.HandleListOrphanIds(1, tmp.Tracker);

            Assert.IsTrue(result.Contains("gone_widget_1"),
                $"gone_widget_1 must be an orphan: {result}");
            Assert.IsTrue(result.Contains("gone_widget_2"),
                $"gone_widget_2 must be an orphan: {result}");
        }

        [Test]
        public void ListOrphanIdsDoesNotIncludeLiveNodes()
        {
            using var tmp = new TempTrackerScope();
            var go = MakeWidget("LiveNode_OrphanTest");

            string liveId = FindNodeId(go);
            Assert.IsNotNull(liveId, "live node must appear in dump");

            // Previous scan contains a live id and a gone id.
            tmp.Tracker.Save(new[] { liveId, "truly_gone_node" });

            string result = PinIdHandler.HandleListOrphanIds(1, tmp.Tracker);

            Assert.IsTrue(result.Contains("truly_gone_node"),
                $"gone node must be an orphan: {result}");
            Assert.IsFalse(result.Contains(liveId),
                $"live node must NOT be an orphan: {result}");
        }

        [Test]
        public void ListOrphanIdsNullTrackerReturnsEmptyArray()
        {
            string result = PinIdHandler.HandleListOrphanIds(1, null);
            Assert.IsTrue(result.Contains("[]"),
                $"null tracker → must return []: {result}");
        }

        [Test]
        public void DumpTreeUpdatesScanForSubsequentListOrphanIds()
        {
            using var tmp = new TempTrackerScope();
            var dispatcher = new MainThreadDispatcher();
            var handler    = new ProtocolHandler(dispatcher, tmp.Tracker);

            // Create a widget and run dump_tree so the tracker records its id.
            var go = MakeWidget("DumpThenOrphan");
            string liveId = FindNodeId(go);
            Assert.IsNotNull(liveId);

            // Enqueue dump_tree and flush so it runs and saves to tracker.
            string dumpResponse = null;
            handler.Enqueue(
                "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"dump_tree\",\"params\":{}}",
                r => dumpResponse = r);
            handler.DrainOnMainThread();

            Assert.IsNotNull(dumpResponse, "dump_tree must have replied");
            Assert.IsTrue(dumpResponse.Contains(liveId),
                "dump response must contain the live node's id");

            // Destroy the widget so it becomes an orphan.
            Object.DestroyImmediate(go);
            _created.Remove(go);

            // list_orphan_ids should now report the old id as an orphan.
            string orphanResponse = PinIdHandler.HandleListOrphanIds(2, tmp.Tracker);
            Assert.IsTrue(orphanResponse.Contains(liveId),
                $"destroyed node must appear as orphan: {orphanResponse}");
        }

        // ------------------------------------------------------------------ helpers

        sealed class TempTrackerScope : System.IDisposable
        {
            public readonly OrphanTracker Tracker;
            readonly string _dir;

            public TempTrackerScope()
            {
                _dir    = Path.Combine(Path.GetTempPath(),
                              "AutoAgentTests_" + System.Guid.NewGuid().ToString("N"));
                Directory.CreateDirectory(_dir);
                Tracker = new OrphanTracker(Path.Combine(_dir, "last_scan.json"));
            }

            public void Dispose()
            {
                try { Directory.Delete(_dir, recursive: true); } catch { }
            }
        }
    }
}
