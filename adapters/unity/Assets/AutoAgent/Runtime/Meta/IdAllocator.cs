using System.Collections.Generic;
using System.Text;
using UnityEngine;

namespace AutoAgent
{
    /// <summary>
    /// Assigns a stable identifier and a <c>stable_id_source</c> to every
    /// RectTransform UI node in a scene.
    ///
    /// Rules (docs/01-protocol-spec.md §三):
    ///   • A node carrying a <see cref="StableIdComponent"/> with a non-empty
    ///     <c>pinnedId</c> uses that id verbatim — source "pinned".
    ///   • Every other node gets a derived id — source "hash" — built from the
    ///     sanitized GameObject name. When several nodes share a name the
    ///     colliding ids gain a numeric suffix (_2, _3 …).
    ///
    /// Suffix assignment is made deterministic by ordering the colliding nodes
    /// on a stable FNV-1a hash of their hierarchy path, so a node keeps its id
    /// even if unrelated siblings are reordered in the scene.
    /// </summary>
    internal sealed class IdAllocator
    {
        readonly Dictionary<Transform, string> _ids = new Dictionary<Transform, string>();
        readonly Dictionary<Transform, string> _sources = new Dictionary<Transform, string>();
        readonly Dictionary<string, Transform> _byId = new Dictionary<string, Transform>();
        readonly HashSet<string> _used = new HashSet<string>();

        public string IdOf(Transform t) => _ids.TryGetValue(t, out var id) ? id : null;
        public string SourceOf(Transform t) => _sources.TryGetValue(t, out var s) ? s : null;
        public Transform TransformFor(string id) => _byId.TryGetValue(id, out var t) ? t : null;

        /// <summary>Walk the scene roots and allocate ids for every UI node.</summary>
        public static IdAllocator Allocate(IEnumerable<GameObject> roots)
        {
            var alloc = new IdAllocator();
            var all = new List<Transform>();
            foreach (var root in roots)
                if (root != null)
                    alloc.Flatten(root.transform, all);

            // Pass 1: pinned ids — authoritative, reserved first.
            foreach (var t in all)
            {
                if (t.TryGetComponent<StableIdComponent>(out var sid) &&
                    !string.IsNullOrEmpty(sid.pinnedId))
                {
                    alloc.Assign(t, alloc.MakeUnique(sid.pinnedId), "pinned");
                }
            }

            // Pass 2: derived ids — group remaining nodes by sanitized name and
            // assign suffixes in PathHash order for stability.
            var byName = new Dictionary<string, List<Transform>>();
            foreach (var t in all)
            {
                if (alloc._ids.ContainsKey(t)) continue;
                string name = Sanitize(t.name);
                if (!byName.TryGetValue(name, out var bucket))
                    byName[name] = bucket = new List<Transform>();
                bucket.Add(t);
            }
            foreach (var pair in byName)
            {
                var bucket = pair.Value;
                bucket.Sort((a, b) => string.CompareOrdinal(
                    alloc.PathHash(a) + a.GetInstanceID().ToString("x8"),
                    alloc.PathHash(b) + b.GetInstanceID().ToString("x8")));
                foreach (var t in bucket)
                    alloc.Assign(t, alloc.MakeUnique(pair.Key), "hash");
            }
            return alloc;
        }

        void Flatten(Transform t, List<Transform> into)
        {
            if (t.GetComponent<RectTransform>() != null)
                into.Add(t);
            foreach (Transform c in t)
                Flatten(c, into);
        }

        void Assign(Transform t, string id, string source)
        {
            _ids[t] = id;
            _sources[t] = source;
            _byId[id] = t;
        }

        // Returns baseId if free, else baseId_2 / baseId_3 / …
        string MakeUnique(string baseId)
        {
            if (string.IsNullOrEmpty(baseId)) baseId = "node";
            if (_used.Add(baseId)) return baseId;
            for (int i = 2; ; i++)
            {
                string candidate = baseId + "_" + i;
                if (_used.Add(candidate)) return candidate;
            }
        }

        // ---- hierarchy path hash (the "hash algorithm") --------------------

        /// <summary>8-hex FNV-1a hash of the node's full hierarchy path. Stable
        /// across runs as long as the ancestor names are unchanged.</summary>
        public string PathHash(Transform t) => Fnv1a(PathOf(t)).ToString("x8");

        internal static string PathOf(Transform t)
        {
            var parts = new List<string>();
            for (var cur = t; cur != null; cur = cur.parent)
                parts.Add(cur.name);
            parts.Reverse();
            return string.Join("/", parts);
        }

        internal static uint Fnv1a(string s)
        {
            const uint offset = 2166136261u;
            const uint prime = 16777619u;
            uint h = offset;
            if (s != null)
            {
                foreach (char ch in s)
                {
                    h ^= ch;
                    h *= prime;
                }
            }
            return h;
        }

        // Replace anything that is not a letter or digit with '_'.
        internal static string Sanitize(string name)
        {
            if (string.IsNullOrEmpty(name)) return "node";
            var sb = new StringBuilder(name.Length);
            foreach (char ch in name)
                sb.Append(char.IsLetterOrDigit(ch) ? ch : '_');
            return sb.ToString();
        }
    }
}
