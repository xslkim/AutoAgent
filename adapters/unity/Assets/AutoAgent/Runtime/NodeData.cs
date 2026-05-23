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
        public string StableIdSource; // "pinned" | "auto" | "hash"
        public VisualData Visual;
        public BehaviorData Behavior;
        public MetaData Meta;
    }

    internal class VisualData
    {
        public float[] Position;    // [x, y] anchoredPosition
        public float[] Size;        // [w, h]
        public float[] Anchor;      // [x, y] anchorMin
        public bool Visible;
        public float? Alpha;        // 0..1 — CanvasGroup, else Graphic color alpha
        public string Color;        // "#RRGGBBAA" or null
        public string SpriteRef;    // sprite / texture name or null
        public float[] WorldBounds; // [xMin, yMin, xMax, yMax] or null
        public float? ZOrder;       // draw order hint (sibling index)
    }

    internal class BehaviorData
    {
        public bool? Interactable;
        public bool? RaycastTarget;
        // Event entry points this node exposes (e.g. onClick, onValueChanged).
        public List<string> EventHandlers = new List<string>();
        // Non-engine MonoBehaviours attached to this node (project / AI scripts).
        public List<string> CustomScripts = new List<string>();
        // Interactive UI components present (Button / Toggle / TMP_InputField ...).
        // Empty on a bare fixture node; populated once AI wires interactivity.
        public List<string> AttachedComponents = new List<string>();
    }

    internal class MetaData
    {
        public string LogicalRole;  // protocol enum value, e.g. "button"
        public string Intent;       // free-form purpose, or null
        public List<string> Tags;   // classification tags, or null
        public Dictionary<string, string> StateSprites;
    }
}
