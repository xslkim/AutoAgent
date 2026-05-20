// AUTOAGENT_ALLOW_VISUAL: test code toggles GameObject.SetActive on throwaway
// fixture nodes to exercise the "disappeared / visible" wait conditions —
// this is test setup, not a product visual change, so 防护 0.2 is exempted.
using System.Collections;
using NUnit.Framework;
using TMPro;
using UnityEngine;
using UnityEngine.TestTools;
using UnityEngine.UI;

namespace AutoAgent.Tests
{
    /// <summary>
    /// Tests for WaitConditions (TASK-0111).
    /// CheckCondition is the pure predicate (tested synchronously);
    /// the WaitFor coroutine is driven with an injected fake clock so the
    /// timeout path can be exercised deterministically — no reliance on
    /// real time and therefore safe in -batchmode CI.
    /// </summary>
    public class WaitForTests
    {
        readonly System.Collections.Generic.List<GameObject> _spawned =
            new System.Collections.Generic.List<GameObject>();

        [TearDown]
        public void TearDown()
        {
            foreach (var go in _spawned)
                if (go != null) Object.DestroyImmediate(go);
            _spawned.Clear();
        }

        GameObject Spawn(string name, params System.Type[] components)
        {
            var go = new GameObject(name, components);
            _spawned.Add(go);
            return go;
        }

        // ---- CheckCondition: widget_appeared / disappeared -----------------

        [Test]
        public void AppearedTrueForActiveNode()
        {
            Spawn("ActiveNode", typeof(RectTransform));
            Assert.IsTrue(WaitConditions.CheckCondition("widget_appeared", "ActiveNode", null));
        }

        [Test]
        public void AppearedFalseForInactiveNode()
        {
            var go = Spawn("InactiveNode", typeof(RectTransform));
            go.SetActive(false);
            Assert.IsFalse(WaitConditions.CheckCondition("widget_appeared", "InactiveNode", null));
        }

        [Test]
        public void AppearedFalseForMissingNode()
        {
            Assert.IsFalse(WaitConditions.CheckCondition("widget_appeared", "no_such_node", null));
        }

        [Test]
        public void DisappearedTrueForMissingNode()
        {
            Assert.IsTrue(WaitConditions.CheckCondition("widget_disappeared", "no_such_node", null));
        }

        [Test]
        public void DisappearedTrueForInactiveNode()
        {
            var go = Spawn("Inactive", typeof(RectTransform));
            go.SetActive(false);
            Assert.IsTrue(WaitConditions.CheckCondition("widget_disappeared", "Inactive", null));
        }

        // ---- CheckCondition: visible ---------------------------------------

        [Test]
        public void VisibleFalseWhenCanvasGroupAlphaZero()
        {
            var go = Spawn("Hidden", typeof(RectTransform), typeof(CanvasGroup));
            go.GetComponent<CanvasGroup>().alpha = 0f;
            Assert.IsFalse(WaitConditions.CheckCondition("visible", "Hidden", null));
        }

        [Test]
        public void VisibleTrueForActiveNodeWithFullAlpha()
        {
            var go = Spawn("Shown", typeof(RectTransform), typeof(CanvasGroup));
            go.GetComponent<CanvasGroup>().alpha = 1f;
            Assert.IsTrue(WaitConditions.CheckCondition("visible", "Shown", null));
        }

        // ---- CheckCondition: text_changed ----------------------------------

        [Test]
        public void TextChangedTrueWhenTmpTextDiffersFromBaseline()
        {
            var go = Spawn("Label", typeof(RectTransform));
            var tmp = go.AddComponent<TextMeshProUGUI>();
            tmp.text = "new value";
            Assert.IsTrue(WaitConditions.CheckCondition("text_changed", "Label", "old baseline"));
        }

        [Test]
        public void TextChangedFalseWhenTextMatchesBaseline()
        {
            var go = Spawn("Label", typeof(RectTransform));
            var tmp = go.AddComponent<TextMeshProUGUI>();
            tmp.text = "same";
            Assert.IsFalse(WaitConditions.CheckCondition("text_changed", "Label", "same"));
        }

        [Test]
        public void TextChangedFalseWhenNodeMissing()
        {
            // A vanished node is "disappeared", not "text_changed".
            Assert.IsFalse(WaitConditions.CheckCondition("text_changed", "no_such", "baseline"));
        }

        // ---- bad input -----------------------------------------------------

        [Test]
        public void UnknownConditionThrowsInvalidParams()
        {
            var ex = Assert.Throws<WireException>(
                () => WaitConditions.CheckCondition("not_a_condition", "x", null));
            Assert.AreEqual(WireError.InvalidParams, ex.Code);
        }

        [Test]
        public void EmptyConditionThrowsInvalidParams()
        {
            var ex = Assert.Throws<WireException>(
                () => WaitConditions.CheckCondition("", "x", null));
            Assert.AreEqual(WireError.InvalidParams, ex.Code);
        }

        // ---- coroutine: success path ---------------------------------------

        [UnityTest]
        public IEnumerator WaitForResolvesImmediatelyWhenConditionAlreadyTrue()
        {
            Spawn("ReadyNode", typeof(RectTransform));
            // Condition is already true → coroutine finishes on first MoveNext.
            yield return WaitConditions.WaitFor("widget_appeared", "ReadyNode", null, 500);
            // Reaching here means the coroutine completed without exception.
            Assert.Pass();
        }

        // ---- coroutine: timeout path with fake clock -----------------------

        [Test]
        public void WaitForThrowsTimeoutAfterDeadline()
        {
            // Condition never satisfied (no such node, condition=widget_appeared).
            // Fake clock makes the timeout path deterministic, no real-time wait.
            float fakeNow = 0f;
            var co = WaitConditions.WaitFor("widget_appeared", "ghost",
                                            null, 100, () => fakeNow);

            // First iteration: condition false, deadline not yet exceeded
            // (fakeNow=0, deadline=0.1) → yields null.
            Assert.IsTrue(co.MoveNext(), "first poll should yield");

            // Advance past the deadline; the next poll must throw -32005.
            fakeNow = 1.0f;
            var ex = Assert.Throws<WireException>(() => co.MoveNext());
            Assert.AreEqual(WireError.Timeout, ex.Code);
        }
    }
}
