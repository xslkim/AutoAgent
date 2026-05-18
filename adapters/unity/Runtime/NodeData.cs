using System.Collections.Generic;

namespace AutoAgent
{
    internal class NodeData
    {
        public string Id;
        public string Type;
        public string EngineType;
        public string ParentId;
        public List<string> ChildrenIds = new List<string>();
        public string StableIdSource; // "pinned" | "auto"
        public VisualData Visual;
        public BehaviorData Behavior;
        public MetaData Meta;
    }

    internal class VisualData
    {
        public float[] Position;  // [x, y] anchoredPosition
        public float[] Size;      // [w, h]
        public bool Visible;
        public float? Alpha;
        public string Color;      // "#RRGGBBAA" or null
        public string SpriteRef;  // sprite name or null
        public float[] WorldBounds; // [xMin, yMin, xMax, yMax] or null
    }

    internal class BehaviorData
    {
        public bool? Interactable;
        public bool? RaycastTarget;
    }

    internal class MetaData
    {
        public string LogicalRole;  // protocol enum value, e.g. "button"
        public Dictionary<string, string> StateSprites;
    }
}
