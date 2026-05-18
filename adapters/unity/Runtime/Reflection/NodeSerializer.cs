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
            sb.Append("{\"position\":[").Append(v.Position[0].ToString("F2")).Append(',')
              .Append(v.Position[1].ToString("F2")).Append("],");
            sb.Append("\"size\":[").Append(v.Size[0].ToString("F2")).Append(',')
              .Append(v.Size[1].ToString("F2")).Append("],");
            sb.Append("\"visible\":").Append(v.Visible ? "true" : "false");
            if (v.Alpha.HasValue)
                sb.Append(",\"alpha\":").Append(v.Alpha.Value.ToString("F3"));
            if (v.Color != null)
            { sb.Append(','); AppendStr(sb, "color", v.Color); }
            if (v.SpriteRef != null)
            { sb.Append(','); AppendStr(sb, "sprite_ref", v.SpriteRef); }
            if (v.WorldBounds != null)
                sb.Append(",\"world_bounds\":[")
                  .Append(v.WorldBounds[0].ToString("F2")).Append(',')
                  .Append(v.WorldBounds[1].ToString("F2")).Append(',')
                  .Append(v.WorldBounds[2].ToString("F2")).Append(',')
                  .Append(v.WorldBounds[3].ToString("F2")).Append(']');
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
            }
            sb.Append('}');
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
