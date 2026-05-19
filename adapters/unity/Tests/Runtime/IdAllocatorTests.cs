using System.Collections.Generic;
using NUnit.Framework;
using UnityEngine;

namespace AutoAgent.Tests
{
    /// <summary>
    /// Tests for IdAllocator — stable id + source assignment.
    /// Plain [Test]: IdAllocator.Allocate is synchronous and works on any
    /// GameObject roots, no active-scene setup required.
    /// </summary>
    public class IdAllocatorTests
    {
        readonly List<GameObject> _spawned = new List<GameObject>();

        [TearDown]
        public void TearDown()
        {
            foreach (var go in _spawned)
                if (go != null) Object.DestroyImmediate(go);
            _spawned.Clear();
        }

        GameObject Rect(string name, Transform parent = null)
        {
            var go = new GameObject(name);
            _spawned.Add(go);
            go.AddComponent<RectTransform>();
            if (parent != null) go.transform.SetParent(parent, false);
            return go;
        }

        // ---- source classification -----------------------------------------

        [Test]
        public void PinnedNodeReportsPinnedSource()
        {
            var go = Rect("RawName");
            go.AddComponent<StableIdComponent>().pinnedId = "login_button";

            var alloc = IdAllocator.Allocate(new[] { go });

            Assert.AreEqual("login_button", alloc.IdOf(go.transform));
            Assert.AreEqual("pinned", alloc.SourceOf(go.transform));
        }

        [Test]
        public void UnpinnedNodeReportsHashSource()
        {
            var go = Rect("Panel");

            var alloc = IdAllocator.Allocate(new[] { go });

            Assert.AreEqual("hash", alloc.SourceOf(go.transform));
        }

        [Test]
        public void UniqueNameBecomesPlainId()
        {
            var go = Rect("Panel");
            var alloc = IdAllocator.Allocate(new[] { go });
            Assert.AreEqual("Panel", alloc.IdOf(go.transform));
        }

        // ---- duplicate name → sequence suffix ------------------------------

        [Test]
        public void DuplicateNamesGetSequenceSuffix()
        {
            var root = Rect("Root");
            var a = Rect("Item", root.transform);
            var b = Rect("Item", root.transform);
            var c = Rect("Item", root.transform);

            var alloc = IdAllocator.Allocate(new[] { root });

            var ids = new HashSet<string>
            {
                alloc.IdOf(a.transform),
                alloc.IdOf(b.transform),
                alloc.IdOf(c.transform),
            };
            // Three distinct ids: the base name plus _2 / _3 suffixes.
            Assert.AreEqual(3, ids.Count, "duplicate names must yield unique ids");
            Assert.IsTrue(ids.Contains("Item"));
            Assert.IsTrue(ids.Contains("Item_2"));
            Assert.IsTrue(ids.Contains("Item_3"));
        }

        [Test]
        public void DistinctParentsWithSameNameGetDistinctIds()
        {
            // "Label" under two different parents — different hierarchy paths,
            // both still resolve to unique ids.
            var root = Rect("Root");
            var panelA = Rect("PanelA", root.transform);
            var panelB = Rect("PanelB", root.transform);
            var la = Rect("Label", panelA.transform);
            var lb = Rect("Label", panelB.transform);

            var alloc = IdAllocator.Allocate(new[] { root });

            Assert.AreNotEqual(alloc.IdOf(la.transform), alloc.IdOf(lb.transform));
        }

        // ---- pinned id verbatim + collision --------------------------------

        [Test]
        public void PinnedIdIsUsedVerbatim()
        {
            var go = Rect("whatever");
            go.AddComponent<StableIdComponent>().pinnedId = "my.custom-id_42";
            var alloc = IdAllocator.Allocate(new[] { go });
            Assert.AreEqual("my.custom-id_42", alloc.IdOf(go.transform));
        }

        [Test]
        public void HashIdDoesNotCollideWithAPinnedId()
        {
            // A pinned node reserves "Panel"; a plain node also named Panel
            // must get a suffixed id rather than clashing.
            var root = Rect("Root");
            var pinned = Rect("Anything", root.transform);
            pinned.AddComponent<StableIdComponent>().pinnedId = "Panel";
            var plain = Rect("Panel", root.transform);

            var alloc = IdAllocator.Allocate(new[] { root });

            Assert.AreEqual("Panel", alloc.IdOf(pinned.transform));
            Assert.AreNotEqual("Panel", alloc.IdOf(plain.transform));
            Assert.AreEqual("hash", alloc.SourceOf(plain.transform));
        }

        // ---- reverse lookup -------------------------------------------------

        [Test]
        public void TransformForResolvesAssignedId()
        {
            var go = Rect("Lookup");
            var alloc = IdAllocator.Allocate(new[] { go });
            string id = alloc.IdOf(go.transform);
            Assert.AreSame(go.transform, alloc.TransformFor(id));
            Assert.IsNull(alloc.TransformFor("no-such-id"));
        }

        // ---- node filtering -------------------------------------------------

        [Test]
        public void NonRectTransformNodesAreSkipped()
        {
            var root = Rect("Root");
            var plain = new GameObject("PlainGO"); // no RectTransform
            _spawned.Add(plain);
            plain.transform.SetParent(root.transform, false);

            var alloc = IdAllocator.Allocate(new[] { root });

            Assert.IsNull(alloc.IdOf(plain.transform), "non-UI node must not get an id");
            Assert.IsNotNull(alloc.IdOf(root.transform));
        }

        // ---- hash algorithm -------------------------------------------------

        [Test]
        public void Fnv1aIsDeterministicAndPathSensitive()
        {
            Assert.AreEqual(IdAllocator.Fnv1a("Canvas/Panel/Button"),
                            IdAllocator.Fnv1a("Canvas/Panel/Button"));
            Assert.AreNotEqual(IdAllocator.Fnv1a("Canvas/Panel/Button"),
                               IdAllocator.Fnv1a("Canvas/Panel/Label"));
        }

        [Test]
        public void SanitizeReplacesNonAlphanumericChars()
        {
            Assert.AreEqual("My_Button_", IdAllocator.Sanitize("My Button!"));
            Assert.AreEqual("node", IdAllocator.Sanitize(""));
        }
    }
}
