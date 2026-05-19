using System;
using System.Collections.Generic;
using UnityEngine;

namespace AutoAgent
{
    /// <summary>
    /// Attach to any UI GameObject to assign a stable, pinned identifier and
    /// semantic metadata used by the AutoAgent wire protocol.
    /// </summary>
    [DisallowMultipleComponent]
    public class StableIdComponent : MonoBehaviour
    {
        [Tooltip("Stable identifier referenced by task DSL. Must be unique in the scene.")]
        public string pinnedId;

        [Tooltip("Semantic role of this widget (maps to protocol logical_role).")]
        public AutoAgentLogicalRole logicalRole = AutoAgentLogicalRole.None;

        [Tooltip("Free-form description of what this widget is for (maps to protocol meta.intent).")]
        public string intent;

        [Tooltip("Arbitrary classification tags (maps to protocol meta.tags).")]
        public List<string> tags = new List<string>();

        [Tooltip("State → sprite-path pairs (e.g. normal, hover, pressed, focused, disabled).")]
        public List<StateSpritePair> stateSprites = new List<StateSpritePair>();
    }

    public enum AutoAgentLogicalRole
    {
        None,
        DragSource,
        DropTarget,
        Button,
        Input,
        Slider,
        Toggle,
        Checkbox,
        Dropdown,
        Combobox,
        ScrollContainer,
        ListView,
        TextDisplay,
        ImageOnly,
    }

    [Serializable]
    public class StateSpritePair
    {
        public string state;   // "normal" | "hover" | "pressed" | "focused" | "disabled"
        public string spritePath;
    }
}
