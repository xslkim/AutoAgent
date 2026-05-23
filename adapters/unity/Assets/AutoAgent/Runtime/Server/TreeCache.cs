using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
using UnityEngine;

namespace AutoAgent
{
    /// <summary>
    /// Result returned by <see cref="TreeCache.Diff"/>.
    /// </summary>
    internal struct DeltaResult
    {
        public string      snapshotId;
        public List<NodeData> changed;
        public List<string>   removedIds;
        public int            unchangedCount;
        public bool           fullSnapshot;

        public static DeltaResult Full(List<NodeData> nodes, string snapshotId) =>
            new DeltaResult
            {
                snapshotId     = snapshotId,
                changed        = nodes,
                removedIds     = new List<string>(),
                unchangedCount = 0,
                fullSnapshot   = true,
            };
    }

    /// <summary>
    /// In-memory snapshot cache that computes deltas between two
    /// <c>dump_tree</c> calls, returning only added / modified / removed
    /// nodes.
    ///
    /// <para>Thread-safe: all public methods acquire a lock internally.</para>
    /// <para>Keeps at most <c>MaxSnapshots</c> entries (default 20),
    /// evicting the oldest on overflow.</para>
    /// </summary>
    internal static class TreeCache
    {
        const int DefaultMaxSnapshots = 20;

        static readonly object _lock = new object();
        static readonly Dictionary<string, Dictionary<string, string>> _snapshots =
            new Dictionary<string, Dictionary<string, string>>();
        static readonly List<string> _order = new List<string>();
        static int _maxSnapshots = DefaultMaxSnapshots;

        // ------------------------------------------------------------------
        // Public API
        // ------------------------------------------------------------------

        /// <summary>
        /// Store a full node list as a new snapshot.  Returns an 8-char hex
        /// snapshot ID for use in a subsequent <see cref="Diff"/> call.
        /// </summary>
        public static string Store(List<NodeData> nodes)
        {
            string snapId = GenerateId();
            var mapping = new Dictionary<string, string>();
            foreach (var n in nodes)
            {
                if (string.IsNullOrEmpty(n.Id)) continue;
                mapping[n.Id] = ComputeNodeHash(n);
            }
            lock (_lock)
            {
                _snapshots[snapId] = mapping;
                _order.Add(snapId);
                EvictLocked();
            }
            return snapId;
        }

        /// <summary>
        /// Compute the delta between the baseline snapshot *sinceId* and
        /// *newNodes*.  Always stores *newNodes* as a fresh snapshot.
        ///
        /// When *sinceId* is unknown (expired / never existed) the result
        /// has <see cref="DeltaResult.fullSnapshot"/> == true.
        /// </summary>
        public static DeltaResult Diff(string sinceId, List<NodeData> newNodes)
        {
            Dictionary<string, string> baseline;
            lock (_lock) { _snapshots.TryGetValue(sinceId ?? "", out baseline); }

            if (baseline == null)
            {
                string snapId = Store(newNodes);
                return DeltaResult.Full(newNodes, snapId);
            }

            // Build new mapping.
            var newMap = new Dictionary<string, (NodeData node, string hash)>();
            foreach (var n in newNodes)
            {
                if (string.IsNullOrEmpty(n.Id)) continue;
                newMap[n.Id] = (n, ComputeNodeHash(n));
            }

            var changed = new List<NodeData>();
            int unchanged = 0;
            foreach (var (nid, (node, hash)) in newMap)
            {
                if (!baseline.TryGetValue(nid, out var oldHash) || oldHash != hash)
                    changed.Add(node);
                else
                    unchanged++;
            }

            var removed = new List<string>();
            foreach (var nid in baseline.Keys)
                if (!newMap.ContainsKey(nid))
                    removed.Add(nid);

            string newId = Store(newNodes);
            return new DeltaResult
            {
                snapshotId     = newId,
                changed        = changed,
                removedIds     = removed,
                unchangedCount = unchanged,
                fullSnapshot   = false,
            };
        }

        /// <summary>Remove all cached snapshots.</summary>
        public static void Clear()
        {
            lock (_lock) { _snapshots.Clear(); _order.Clear(); }
        }

        /// <summary>Number of snapshots currently stored.</summary>
        public static int SnapshotCount { get { lock (_lock) return _snapshots.Count; } }

        // ------------------------------------------------------------------
        // Internals
        // ------------------------------------------------------------------

        static string GenerateId()
        {
            var bytes = new byte[4];
            using (var rng = RandomNumberGenerator.Create())
                rng.GetBytes(bytes);
            var sb = new StringBuilder(8);
            foreach (var b in bytes) sb.AppendFormat("{0:x2}", b);
            return sb.ToString();
        }

        static string ComputeNodeHash(NodeData node)
        {
            var sb = new StringBuilder();
            sb.Append(node.Id); sb.Append('|');
            sb.Append(node.Type); sb.Append('|');
            sb.Append(node.EngineType); sb.Append('|');
            sb.Append(node.ParentId ?? ""); sb.Append('|');
            sb.Append(string.Join(",", node.ChildrenIds)); sb.Append('|');
            sb.Append(node.StableIdSource ?? ""); sb.Append('|');

            var v = node.Visual;
            sb.Append(v.Position?[0] ?? 0); sb.Append(','); sb.Append(v.Position?[1] ?? 0); sb.Append('|');
            sb.Append(v.Size?[0] ?? 0); sb.Append(','); sb.Append(v.Size?[1] ?? 0); sb.Append('|');
            sb.Append(v.Anchor?[0] ?? 0); sb.Append(','); sb.Append(v.Anchor?[1] ?? 0); sb.Append('|');
            sb.Append(v.Visible); sb.Append('|');
            sb.Append(v.Alpha); sb.Append('|');
            sb.Append(v.Color ?? ""); sb.Append('|');
            sb.Append(v.SpriteRef ?? ""); sb.Append('|');
            if (v.WorldBounds != null && v.WorldBounds.Length == 4)
            { sb.Append(v.WorldBounds[0]); sb.Append(','); sb.Append(v.WorldBounds[1]);
              sb.Append(','); sb.Append(v.WorldBounds[2]); sb.Append(','); sb.Append(v.WorldBounds[3]); }
            sb.Append('|'); sb.Append(v.ZOrder); sb.Append('|');

            var b = node.Behavior;
            sb.Append(b.Interactable); sb.Append('|');
            sb.Append(b.RaycastTarget); sb.Append('|');
            sb.Append(string.Join(",", b.EventHandlers)); sb.Append('|');
            sb.Append(string.Join(",", b.CustomScripts)); sb.Append('|');
            sb.Append(string.Join(",", b.AttachedComponents)); sb.Append('|');

            var m = node.Meta;
            if (m != null)
            {
                sb.Append(m.LogicalRole ?? ""); sb.Append('|');
                sb.Append(m.Intent ?? ""); sb.Append('|');
                sb.Append(string.Join(",", m.Tags ?? new List<string>())); sb.Append('|');
                if (m.StateSprites != null)
                    foreach (var kv in m.StateSprites)
                    { sb.Append(kv.Key); sb.Append('='); sb.Append(kv.Value); sb.Append(';'); }
            }

            using (var sha = SHA256.Create())
            {
                var bytes = sha.ComputeHash(Encoding.UTF8.GetBytes(sb.ToString()));
                var hashSb = new StringBuilder(bytes.Length * 2);
                foreach (var bt in bytes) hashSb.AppendFormat("{0:x2}", bt);
                return hashSb.ToString();
            }
        }

        static void EvictLocked()
        {
            while (_order.Count > _maxSnapshots)
            {
                string old = _order[0];
                _order.RemoveAt(0);
                _snapshots.Remove(old);
            }
        }
    }
}
