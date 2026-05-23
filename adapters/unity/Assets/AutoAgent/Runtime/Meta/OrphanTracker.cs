using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace AutoAgent
{
    /// <summary>
    /// Tracks UI node ids across dumps.
    ///
    /// After each dump the current id set is persisted to
    /// <c>Library/AutoAgent/last_scan.json</c>; the next dump diffs against it
    /// to surface three categories:
    ///   • <b>orphans</b>  — ids present in the previous scan but gone now
    ///                       (a node was deleted, or its hierarchy changed so
    ///                       its hash id shifted).
    ///   • <b>found</b>    — ids present in both scans (stable nodes).
    ///   • <b>appeared</b> — ids new in this scan.
    ///
    /// Powers the <c>list_orphan_ids</c> wire method (wired up in TASK-0116).
    /// The state file lives under Library/, which is gitignored.
    /// </summary>
    internal sealed class OrphanTracker
    {
        [Serializable]
        private class ScanState
        {
            public List<string> ids = new List<string>();
        }

        private readonly string _statePath;

        public OrphanTracker(string statePath)
        {
            _statePath = statePath;
        }

        /// <summary>An OrphanTracker writing under the project's Library folder.</summary>
        public static OrphanTracker ForProject()
        {
            return new OrphanTracker(DefaultStatePath());
        }

        /// <summary>&lt;project&gt;/Library/AutoAgent/last_scan.json (absolute).</summary>
        public static string DefaultStatePath()
        {
            return Path.GetFullPath(Path.Combine(
                Application.dataPath, "..", "Library", "AutoAgent", "last_scan.json"));
        }

        public string StatePath => _statePath;

        /// <summary>Ids persisted by the previous Reconcile / Save call.</summary>
        public List<string> LoadLastScan()
        {
            if (!File.Exists(_statePath))
                return new List<string>();
            try
            {
                var json = File.ReadAllText(_statePath);
                var state = JsonUtility.FromJson<ScanState>(json);
                return state?.ids ?? new List<string>();
            }
            catch (Exception)
            {
                // A corrupt / unreadable state file must not crash a dump —
                // treat it as "no history".
                return new List<string>();
            }
        }

        /// <summary>
        /// Diff <paramref name="currentIds"/> against the last persisted scan,
        /// then persist the current ids as the new scan.
        /// </summary>
        public OrphanReport Reconcile(IEnumerable<string> currentIds)
        {
            var current = Dedup(currentIds);
            var currentSet = new HashSet<string>(current);

            var previous = LoadLastScan();
            var previousSet = new HashSet<string>(previous);

            var orphans = new List<string>();
            var found = new List<string>();
            foreach (var id in previous)
            {
                if (currentSet.Contains(id)) found.Add(id);
                else orphans.Add(id);
            }

            var appeared = new List<string>();
            foreach (var id in current)
                if (!previousSet.Contains(id))
                    appeared.Add(id);

            Save(current);
            return new OrphanReport(orphans, found, appeared);
        }

        /// <summary>Persist an id set as the new "last scan" without diffing.</summary>
        public void Save(IEnumerable<string> ids)
        {
            var state = new ScanState { ids = Dedup(ids) };
            var dir = Path.GetDirectoryName(_statePath);
            if (!string.IsNullOrEmpty(dir))
                Directory.CreateDirectory(dir);
            File.WriteAllText(_statePath, JsonUtility.ToJson(state));
        }

        /// <summary>Forget the persisted scan (next Reconcile sees no history).</summary>
        public void Reset()
        {
            if (File.Exists(_statePath))
                File.Delete(_statePath);
        }

        private static List<string> Dedup(IEnumerable<string> ids)
        {
            var seen = new HashSet<string>();
            var ordered = new List<string>();
            if (ids != null)
            {
                foreach (var id in ids)
                    if (!string.IsNullOrEmpty(id) && seen.Add(id))
                        ordered.Add(id);
            }
            return ordered;
        }
    }

    /// <summary>Result of one <see cref="OrphanTracker.Reconcile"/> call.</summary>
    internal sealed class OrphanReport
    {
        public readonly List<string> Orphans;   // were present, now gone
        public readonly List<string> Found;     // present in both scans
        public readonly List<string> Appeared;  // new in this scan

        public OrphanReport(List<string> orphans, List<string> found, List<string> appeared)
        {
            Orphans = orphans;
            Found = found;
            Appeared = appeared;
        }
    }
}
