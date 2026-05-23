using System;
using System.Collections.Generic;
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

        static readonly System.Random _rng = new System.Random();

        static string GenerateId()
        {
            // 4 random bytes → 8 hex chars, fast and sufficient for cache keys.
            int val;
            lock (_rng) { val = _rng.Next(); }
            return val.ToString("x8");
        }

        static string ComputeNodeHash(NodeData node)
        {
            var sb = new StringBuilder(256);
            AppendField(sb, node.Id);
            AppendField(sb, node.Type);
            AppendField(sb, node.EngineType);
            AppendField(sb, node.ParentId ?? "");
            AppendField(sb, string.Join(",", node.ChildrenIds));
            AppendField(sb, node.StableIdSource ?? "");

            var v = node.Visual;
            sb.Append(v.Position?[0] ?? 0); sb.Append(','); sb.Append(v.Position?[1] ?? 0); sb.Append('|');
            sb.Append(v.Size?[0] ?? 0); sb.Append(','); sb.Append(v.Size?[1] ?? 0); sb.Append('|');
            sb.Append(v.Anchor?[0] ?? 0); sb.Append(','); sb.Append(v.Anchor?[1] ?? 0); sb.Append('|');
            sb.Append(v.Visible); sb.Append('|');
            sb.Append(v.Alpha); sb.Append('|');
            AppendField(sb, v.Color ?? "");
            AppendField(sb, v.SpriteRef ?? "");
            if (v.WorldBounds != null && v.WorldBounds.Length == 4)
            { sb.Append(v.WorldBounds[0]); sb.Append(','); sb.Append(v.WorldBounds[1]);
              sb.Append(','); sb.Append(v.WorldBounds[2]); sb.Append(','); sb.Append(v.WorldBounds[3]); }
            sb.Append('|'); sb.Append(v.ZOrder); sb.Append('|');

            var b = node.Behavior;
            sb.Append(b.Interactable); sb.Append('|');
            sb.Append(b.RaycastTarget); sb.Append('|');
            AppendField(sb, string.Join(",", b.EventHandlers));
            AppendField(sb, string.Join(",", b.CustomScripts));
            AppendField(sb, string.Join(",", b.AttachedComponents));

            var m = node.Meta;
            if (m != null)
            {
                AppendField(sb, m.LogicalRole ?? "");
                AppendField(sb, m.Intent ?? "");
                AppendField(sb, string.Join(",", m.Tags ?? new List<string>()));
                if (m.StateSprites != null)
                    foreach (var kv in m.StateSprites)
                    { sb.Append(kv.Key); sb.Append('='); sb.Append(kv.Value); sb.Append(';'); }
            }

            // FNV-1a 64-bit: fast non-crypto hash, good distribution for content comparison.
            return Fnv1a64(sb.ToString()).ToString("x16");
        }

        static void AppendField(StringBuilder sb, string val)
        {
            sb.Append(val); sb.Append('|');
        }

        static ulong Fnv1a64(string s)
        {
            const ulong offset = 14695981039346656037UL;
            const ulong prime  = 1099511628211UL;
            ulong hash = offset;
            foreach (char c in s)
            {
                hash ^= (byte)(c & 0xFF);
                hash *= prime;
                hash ^= (byte)(c >> 8);
                hash *= prime;
            }
            return hash;
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
