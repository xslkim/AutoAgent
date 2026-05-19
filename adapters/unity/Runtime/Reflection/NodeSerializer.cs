using System.Collections.Generic;
using System.Text;

namespace AutoAgent
{
    internal static class NodeSerializer
    {
        public static string SerializeTree(List<NodeData> nodes)
        {
            var sb = new StringBuilder(4096);
            sb.Append('[');
            for (int i = 0; i < nodes.Count; i++)
            {
                if (i > 0) sb.Append(',');
                AppendNode(sb, nodes[i]);
            }
            sb.Append(']');
            return sb.ToString();
        }

        static void AppendNode(StringBuilder sb, NodeData n)
        {
            sb.Append('{');
            AppendStr(sb, "id", n.Id); sb.Append(',');
            AppendStr(sb, "type", n.Type); sb.Append(',');
            AppendStr(sb, "engine_type", n.EngineType); sb.Append(',');
            AppendStrOrNull(sb, "parent_id", n.ParentId); sb.Append(',');
            sb.Append("\"children_ids\":[");
            for (int i = 0; i < n.ChildrenIds.Count; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append('"').Append(Esc(n.ChildrenIds[i])).Append('"');
            }
            sb.Append("],");
            AppendStr(sb, "stable_id_source", n.StableIdSource); sb.Append(',');
            sb.Append("\"visual\":"); AppendVisual(sb, n.Visual);
            if (n.Behavior != null) { sb.Append(",\"behavior\":"); AppendBehavior(sb, n.Behavior); }
            if (n.Meta != null)     { sb.Append(",\"meta\":");     AppendMeta(sb, n.Meta); }
            sb.Append('}');
        }

        static void AppendVisual(StringBuilder sb, VisualData v)
        {
            sb.Append("{\"position\":[").Append(Num(v.Position[0])).Append(',')
              .Append(Num(v.Position[1])).Append("],");
            sb.Append("\"size\":[").Append(Num(v.Size[0])).Append(',')
              .Append(Num(v.Size[1])).Append("],");
            if (v.Anchor != null)
                sb.Append("\"anchor\":[").Append(Num(v.Anchor[0])).Append(',')
                  .Append(Num(v.Anchor[1])).Append("],");
            sb.Append("\"visible\":").Append(v.Visible ? "true" : "false");
            if (v.Alpha.HasValue)
                sb.Append(",\"alpha\":").Append(Num(v.Alpha.Value));
            if (v.Color != null)
            { sb.Append(','); AppendStr(sb, "color", v.Color); }
            if (v.SpriteRef != null)
            { sb.Append(','); AppendStr(sb, "sprite_ref", v.SpriteRef); }
            if (v.WorldBounds != null)
                sb.Append(",\"world_bounds\":[")
                  .Append(Num(v.WorldBounds[0])).Append(',')
                  .Append(Num(v.WorldBounds[1])).Append(',')
                  .Append(Num(v.WorldBounds[2])).Append(',')
                  .Append(Num(v.WorldBounds[3])).Append(']');
            if (v.ZOrder.HasValue)
                sb.Append(",\"z_order\":").Append(Num(v.ZOrder.Value));
            sb.Append('}');
        }

        static void AppendBehavior(StringBuilder sb, BehaviorData b)
        {
            sb.Append('{');
            bool first = true;
            if (b.Interactable.HasValue)
            {
                sb.Append("\"interactable\":").Append(b.Interactable.Value ? "true" : "false");
                first = false;
            }
            if (b.RaycastTarget.HasValue)
            {
                if (!first) sb.Append(',');
                sb.Append("\"raycast_target\":").Append(b.RaycastTarget.Value ? "true" : "false");
                first = false;
            }
            if (!first) sb.Append(',');
            AppendStrArray(sb, "event_handlers", b.EventHandlers); sb.Append(',');
            AppendStrArray(sb, "custom_scripts", b.CustomScripts); sb.Append(',');
            AppendStrArray(sb, "attached_components", b.AttachedComponents);
            sb.Append('}');
        }

        static void AppendStrArray(StringBuilder sb, string key, System.Collections.Generic.List<string> values)
        {
            sb.Append('"').Append(Esc(key)).Append("\":[");
            if (values != null)
            {
                for (int i = 0; i < values.Count; i++)
                {
                    if (i > 0) sb.Append(',');
                    sb.Append('"').Append(Esc(values[i])).Append('"');
                }
            }
            sb.Append(']');
        }

        // JSON-safe number: invariant culture, no exponent, finite values only.
        static string Num(float f)
        {
            if (float.IsNaN(f) || float.IsInfinity(f)) return "0";
            return f.ToString("0.##", System.Globalization.CultureInfo.InvariantCulture);
        }

        static void AppendMeta(StringBuilder sb, MetaData m)
        {
            sb.Append('{');
            bool first = true;
            if (m.LogicalRole != null)
            {
                AppendStr(sb, "logical_role", m.LogicalRole);
                first = false;
            }
            if (m.StateSprites != null && m.StateSprites.Count > 0)
            {
                if (!first) sb.Append(',');
                sb.Append("\"state_sprites\":{");
                bool sf = true;
                foreach (var kv in m.StateSprites)
                {
                    if (!sf) sb.Append(',');
                    AppendStr(sb, kv.Key, kv.Value);
                    sf = false;
                }
                sb.Append('}');
            }
            sb.Append('}');
        }

        static void AppendStr(StringBuilder sb, string key, string value) =>
            sb.Append('"').Append(Esc(key)).Append("\":\"").Append(Esc(value)).Append('"');

        static void AppendStrOrNull(StringBuilder sb, string key, string value)
        {
            sb.Append('"').Append(Esc(key)).Append("\":");
            if (value == null) sb.Append("null");
            else sb.Append('"').Append(Esc(value)).Append('"');
        }

        internal static string Esc(string s)
        {
            if (s == null) return "";
            return s.Replace("\\", "\\\\")
                    .Replace("\"", "\\\"")
                    .Replace("\n", "\\n")
                    .Replace("\r", "\\r")
                    .Replace("\t", "\\t");
        }
    }
}
