using System.Collections.Generic;
using NUnit.Framework;

namespace AutoAgent.Tests
{
    [TestFixture]
    public class TreeCacheTests
    {
        [SetUp]
        public void SetUp()
        {
            TreeCache.Clear();
        }

        // ---- Store ----

        [Test]
        public void Store_ReturnsNonEmptyId()
        {
            var nodes = new List<NodeData> { MakeNode("a") };
            string id = TreeCache.Store(nodes);
            Assert.That(id, Is.Not.Null.And.Length.EqualTo(8));
        }

        [Test]
        public void Store_DifferentCallsReturnDifferentIds()
        {
            var nodes = new List<NodeData> { MakeNode("a") };
            string id1 = TreeCache.Store(nodes);
            string id2 = TreeCache.Store(nodes);
            Assert.That(id1, Is.Not.EqualTo(id2));
        }

        [Test]
        public void Store_SkipsNodesWithoutId()
        {
            var nodes = new List<NodeData>
            {
                MakeNode("a"), MakeNode(null), MakeNode("b")
            };
            string id = TreeCache.Store(nodes);
            Assert.That(id, Is.Not.Null);
            Assert.That(TreeCache.SnapshotCount, Is.EqualTo(1));
        }

        [Test]
        public void Store_EmptyList_IsFine()
        {
            string id = TreeCache.Store(new List<NodeData>());
            Assert.That(id, Is.Not.Null);
        }

        // ---- Diff unknown baseline ----

        [Test]
        public void Diff_UnknownBaseline_ReturnsFullSnapshot()
        {
            var nodes = new List<NodeData> { MakeNode("x") };
            var dr = TreeCache.Diff("deadbeef", nodes);
            Assert.That(dr.fullSnapshot, Is.True);
            Assert.That(dr.changed.Count, Is.EqualTo(1));
            Assert.That(dr.changed[0].Id, Is.EqualTo("x"));
            Assert.That(dr.removedIds.Count, Is.EqualTo(0));
            Assert.That(dr.unchangedCount, Is.EqualTo(0));
        }

        // ---- Diff delta ----

        [Test]
        public void Diff_IdenticalNodes_ReturnsEmpty()
        {
            var nodes = new List<NodeData> { MakeNode("a"), MakeNode("b") };
            string snapId = TreeCache.Store(nodes);

            var dr = TreeCache.Diff(snapId, nodes);
            Assert.That(dr.fullSnapshot, Is.False);
            Assert.That(dr.changed.Count, Is.EqualTo(0));
            Assert.That(dr.removedIds.Count, Is.EqualTo(0));
            Assert.That(dr.unchangedCount, Is.EqualTo(2));
        }

        [Test]
        public void Diff_AddedNode()
        {
            var oldNodes = new List<NodeData> { MakeNode("a") };
            string snapId = TreeCache.Store(oldNodes);

            var newNodes = new List<NodeData> { MakeNode("a"), MakeNode("b") };
            var dr = TreeCache.Diff(snapId, newNodes);
            Assert.That(dr.fullSnapshot, Is.False);
            Assert.That(dr.changed.Count, Is.EqualTo(1));
            Assert.That(dr.changed[0].Id, Is.EqualTo("b"));
            Assert.That(dr.removedIds.Count, Is.EqualTo(0));
            Assert.That(dr.unchangedCount, Is.EqualTo(1));
        }

        [Test]
        public void Diff_RemovedNode()
        {
            var oldNodes = new List<NodeData> { MakeNode("a"), MakeNode("b") };
            string snapId = TreeCache.Store(oldNodes);

            var newNodes = new List<NodeData> { MakeNode("a") };
            var dr = TreeCache.Diff(snapId, newNodes);
            Assert.That(dr.fullSnapshot, Is.False);
            Assert.That(dr.changed.Count, Is.EqualTo(0));
            Assert.That(dr.removedIds, Is.EquivalentTo(new[] { "b" }));
            Assert.That(dr.unchangedCount, Is.EqualTo(1));
        }

        [Test]
        public void Diff_ModifiedNode()
        {
            var oldNodes = new List<NodeData> { MakeNode("a", "hello") };
            string snapId = TreeCache.Store(oldNodes);

            var newNodes = new List<NodeData> { MakeNode("a", "world") };
            var dr = TreeCache.Diff(snapId, newNodes);
            Assert.That(dr.fullSnapshot, Is.False);
            Assert.That(dr.changed.Count, Is.EqualTo(1));
            Assert.That(dr.changed[0].Id, Is.EqualTo("a"));
            Assert.That(dr.changed[0].Type, Is.EqualTo("world"));
        }

        // ---- Eviction ----

        [Test]
        public void Eviction_DropsOldestSnapshot()
        {
            // Fill beyond default 20 limit.
            var nodes = new List<NodeData> { MakeNode("a") };
            string firstId = null;
            for (int i = 0; i < 22; i++)
            {
                string id = TreeCache.Store(nodes);
                if (i == 0) firstId = id;
            }

            Assert.That(TreeCache.SnapshotCount, Is.EqualTo(20));
            // The first snapshot should have been evicted.
            var dr = TreeCache.Diff(firstId, nodes);
            Assert.That(dr.fullSnapshot, Is.True);
        }

        // ---- Clear ----

        [Test]
        public void Clear_RemovesAllSnapshots()
        {
            TreeCache.Store(new List<NodeData> { MakeNode("x") });
            TreeCache.Store(new List<NodeData> { MakeNode("y") });
            Assert.That(TreeCache.SnapshotCount, Is.EqualTo(2));
            TreeCache.Clear();
            Assert.That(TreeCache.SnapshotCount, Is.EqualTo(0));
        }

        [Test]
        public void Clear_MakesOldIdUnknown()
        {
            var nodes = new List<NodeData> { MakeNode("x") };
            string snapId = TreeCache.Store(nodes);
            TreeCache.Clear();
            var dr = TreeCache.Diff(snapId, nodes);
            Assert.That(dr.fullSnapshot, Is.True);
        }

        // ---- helpers ----

        static NodeData MakeNode(string id, string type = "Button")
        {
            return new NodeData
            {
                Id = id,
                Type = type,
                EngineType = "UnityEngine.UI.Button",
                Visual = new VisualData
                {
                    Position = new[] { 0f, 0f },
                    Size = new[] { 100f, 40f },
                    Anchor = new[] { 0.5f, 0.5f },
                    Visible = true,
                },
                Behavior = new BehaviorData(),
                ChildrenIds = new List<string>(),
            };
        }
    }
}
