using System;
using System.IO;
using NUnit.Framework;

namespace AutoAgent.Tests
{
    /// <summary>
    /// Tests for OrphanTracker — cross-dump id diffing + JSON persistence.
    /// Plain [Test]: OrphanTracker is file IO + JsonUtility, no scene needed.
    /// Each test uses a unique temp state file ("restart" = a fresh tracker
    /// instance pointed at the same path).
    /// </summary>
    public class OrphanTrackerTests
    {
        string _statePath;

        [SetUp]
        public void SetUp()
        {
            _statePath = Path.Combine(
                Path.GetTempPath(),
                "autoagent_orphan_" + Guid.NewGuid().ToString("N") + ".json");
        }

        [TearDown]
        public void TearDown()
        {
            if (File.Exists(_statePath)) File.Delete(_statePath);
        }

        OrphanTracker NewTracker() => new OrphanTracker(_statePath);

        // ---- verification: first dump → no orphans -------------------------

        [Test]
        public void FirstReconcileHasNoOrphans()
        {
            var report = NewTracker().Reconcile(new[] { "canvas", "panel", "button" });

            Assert.IsEmpty(report.Orphans, "a first dump cannot have orphans");
            Assert.IsEmpty(report.Found, "nothing was tracked before");
            Assert.AreEqual(3, report.Appeared.Count, "all three are newly seen");
        }

        // ---- verification: deleted node → orphan ---------------------------

        [Test]
        public void DeletedNodeBecomesOrphanAfterRestart()
        {
            NewTracker().Reconcile(new[] { "canvas", "panel", "button" });

            // "restart": a fresh tracker reads the persisted scan.
            var report = NewTracker().Reconcile(new[] { "canvas", "panel" });

            CollectionAssert.AreEquivalent(new[] { "button" }, report.Orphans);
            CollectionAssert.AreEquivalent(new[] { "canvas", "panel" }, report.Found);
        }

        // ---- verification: pinned node survives → found --------------------

        [Test]
        public void SurvivingNodeIsFoundAfterRestart()
        {
            NewTracker().Reconcile(new[] { "login_button" });

            var report = NewTracker().Reconcile(new[] { "login_button" });

            CollectionAssert.Contains(report.Found, "login_button");
            Assert.IsEmpty(report.Orphans);
            Assert.IsEmpty(report.Appeared);
        }

        // ---- newly added node ----------------------------------------------

        [Test]
        public void NewNodeShowsUpAsAppeared()
        {
            NewTracker().Reconcile(new[] { "canvas" });

            var report = NewTracker().Reconcile(new[] { "canvas", "panel" });

            CollectionAssert.AreEquivalent(new[] { "panel" }, report.Appeared);
            CollectionAssert.Contains(report.Found, "canvas");
            Assert.IsEmpty(report.Orphans);
        }

        // ---- persistence ----------------------------------------------------

        [Test]
        public void ScanStatePersistsAcrossInstances()
        {
            NewTracker().Reconcile(new[] { "a", "b" });

            var reloaded = NewTracker().LoadLastScan();

            CollectionAssert.AreEquivalent(new[] { "a", "b" }, reloaded);
        }

        [Test]
        public void StateFileIsWrittenToConfiguredPath()
        {
            NewTracker().Reconcile(new[] { "x" });
            Assert.IsTrue(File.Exists(_statePath), "Reconcile must persist a scan file");
        }

        // ---- reset ----------------------------------------------------------

        [Test]
        public void ResetClearsHistory()
        {
            var tracker = NewTracker();
            tracker.Reconcile(new[] { "a", "b" });
            tracker.Reset();

            var report = NewTracker().Reconcile(new[] { "c" });
            Assert.IsEmpty(report.Orphans, "history was reset — nothing can be orphaned");
        }

        // ---- robustness -----------------------------------------------------

        [Test]
        public void CorruptStateFileIsTreatedAsEmpty()
        {
            File.WriteAllText(_statePath, "{ this is not valid json");

            // Must not throw; just behaves as if there were no history.
            var report = NewTracker().Reconcile(new[] { "a" });
            Assert.IsEmpty(report.Orphans);
        }

        [Test]
        public void DuplicateIdsAreDeduped()
        {
            NewTracker().Reconcile(new[] { "a", "a", "b", "b", "b" });

            var reloaded = NewTracker().LoadLastScan();
            CollectionAssert.AreEquivalent(new[] { "a", "b" }, reloaded);
        }

        // ---- default path lives under Library/AutoAgent --------------------

        [Test]
        public void DefaultStatePathLivesUnderLibraryAutoAgent()
        {
            var path = OrphanTracker.DefaultStatePath().Replace('\\', '/');
            StringAssert.Contains("Library/AutoAgent/", path);
            StringAssert.EndsWith("last_scan.json", path);
        }
    }
}
