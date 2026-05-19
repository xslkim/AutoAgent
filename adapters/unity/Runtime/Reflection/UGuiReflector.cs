using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
using UnityEngine.SceneManagement;
using TMPro;

namespace AutoAgent
{
    internal static class UGuiReflector
    {
        /// <summary>
        /// Dump every RectTransform in the active scene into a flat NodeData list.
        /// Parent nodes appear before their children.
        /// </summary>
        public static List<NodeData> DumpActiveScene()
        {
            var nodes = new List<NodeData>();
            var roots = SceneManager.GetActiveScene().GetRootGameObjects();
            // One allocator owns id assignment for the whole dump so that
            // pinned / hash ids and dedup suffixes stay internally consistent.
            var allocator = IdAllocator.Allocate(roots);
            foreach (var root in roots)
                DumpTransform(root.transform, null, nodes, allocator);
            return nodes;
        }

        // Returns the stable ID assigned to this transform, or null if it has no RectTransform.
        static string DumpTransform(Transform t, string parentId, List<NodeData> nodes,
                                    IdAllocator allocator)
        {
            if (!t.TryGetComponent<RectTransform>(out var rt))
                return null;

            string myId = allocator.IdOf(t);
            string idSource = allocator.SourceOf(t) ?? "hash";

            var node = new NodeData
            {
                Id = myId,
                StableIdSource = idSource,
                Type = ResolveType(t.gameObject),
                EngineType = ResolveEngineType(t.gameObject),
                ParentId = parentId,
                ChildrenIds = new List<string>(),
                Visual = BuildVisual(rt, t.gameObject),
                Behavior = BuildBehavior(t.gameObject),
                Meta = BuildMeta(t),
            };
            nodes.Add(node);

            foreach (Transform child in t)
            {
                string childId = DumpTransform(child, myId, nodes, allocator);
                if (childId != null)
                    node.ChildrenIds.Add(childId);
            }
            return myId;
        }

        static string ResolveType(GameObject go)
        {
            if (go.GetComponent<TMP_InputField>() != null)  return "TMP_InputField";
            if (go.GetComponent<TMP_Text>() != null)         return "TMP_Text";
            if (go.GetComponent<InputField>() != null)       return "InputField";
            if (go.GetComponent<Button>() != null)           return "Button";
            if (go.GetComponent<Toggle>() != null)           return "Toggle";
            if (go.GetComponent<Slider>() != null)           return "Slider";
            if (go.GetComponent<ScrollRect>() != null)       return "ScrollRect";
            if (go.GetComponent<Dropdown>() != null)         return "Dropdown";
            if (go.GetComponent<Image>() != null)            return "Image";
            if (go.GetComponent<RawImage>() != null)         return "RawImage";
            if (go.GetComponent<Text>() != null)             return "Text";
            return "RectTransform";
        }

        static string ResolveEngineType(GameObject go)
        {
            if (go.GetComponent<TMP_InputField>() != null)  return "TMPro.TMP_InputField";
            if (go.GetComponent<TMP_Text>() != null)         return "TMPro.TMP_Text";
            if (go.GetComponent<InputField>() != null)       return "UnityEngine.UI.InputField";
            if (go.GetComponent<Button>() != null)           return "UnityEngine.UI.Button";
            if (go.GetComponent<Toggle>() != null)           return "UnityEngine.UI.Toggle";
            if (go.GetComponent<Slider>() != null)           return "UnityEngine.UI.Slider";
            if (go.GetComponent<ScrollRect>() != null)       return "UnityEngine.UI.ScrollRect";
            if (go.GetComponent<Dropdown>() != null)         return "UnityEngine.UI.Dropdown";
            if (go.GetComponent<Image>() != null)            return "UnityEngine.UI.Image";
            if (go.GetComponent<RawImage>() != null)         return "UnityEngine.UI.RawImage";
            if (go.GetComponent<Text>() != null)             return "UnityEngine.UI.Text";
            return "UnityEngine.RectTransform";
        }

        // ---- visual --------------------------------------------------------

        static VisualData BuildVisual(RectTransform rt, GameObject go)
        {
            var corners = new Vector3[4];
            rt.GetWorldCorners(corners);
            // corners: [0]=BL [1]=TL [2]=TR [3]=BR
            float xMin = corners[0].x, yMin = corners[0].y;
            float xMax = corners[2].x, yMax = corners[2].y;

            var v = new VisualData
            {
                Position    = new[] { rt.anchoredPosition.x, rt.anchoredPosition.y },
                Size        = new[] { rt.rect.width, rt.rect.height },
                Anchor      = new[] { rt.anchorMin.x, rt.anchorMin.y },
                Visible     = go.activeInHierarchy,
                WorldBounds = new[] { xMin, yMin, xMax, yMax },
                ZOrder      = rt.GetSiblingIndex(),
            };

            // Graphic carries both color and the effective alpha for a UI node.
            var graphic = go.GetComponent<Graphic>();

            // Alpha: a CanvasGroup overrides; otherwise the Graphic's own color
            // alpha; otherwise a node is treated as fully opaque.
            var cg = go.GetComponent<CanvasGroup>();
            if (cg != null)
                v.Alpha = Mathf.Clamp01(cg.alpha);
            else if (graphic != null)
                v.Alpha = Mathf.Clamp01(graphic.color.a);
            else
                v.Alpha = 1f;

            // Color: any Graphic (Image / RawImage / Text / TMP_Text) exposes one.
            if (graphic != null)
                v.Color = ToHex(graphic.color);

            // Sprite / texture reference.
            var img = go.GetComponent<Image>();
            if (img != null && img.sprite != null)
            {
                v.SpriteRef = img.sprite.name;
            }
            else
            {
                var raw = go.GetComponent<RawImage>();
                if (raw != null && raw.texture != null)
                    v.SpriteRef = raw.texture.name;
            }

            return v;
        }

        static string ToHex(Color c)
        {
            return string.Format("#{0:X2}{1:X2}{2:X2}{3:X2}",
                Mathf.Clamp(Mathf.RoundToInt(c.r * 255f), 0, 255),
                Mathf.Clamp(Mathf.RoundToInt(c.g * 255f), 0, 255),
                Mathf.Clamp(Mathf.RoundToInt(c.b * 255f), 0, 255),
                Mathf.Clamp(Mathf.RoundToInt(c.a * 255f), 0, 255));
        }

        // ---- behavior ------------------------------------------------------

        static BehaviorData BuildBehavior(GameObject go)
        {
            var b = new BehaviorData();

            var selectable = go.GetComponent<Selectable>();
            if (selectable != null)
                b.Interactable = selectable.interactable;

            var graphic = go.GetComponent<Graphic>();
            if (graphic != null)
                b.RaycastTarget = graphic.raycastTarget;

            CollectEventHandlers(go, b.EventHandlers);
            CollectComponents(go, b.CustomScripts, b.AttachedComponents);

            return b;
        }

        // Event entry points the AI can reason about (UnityEvents + EventTrigger
        // entries + EventSystem handler interfaces).
        static void CollectEventHandlers(GameObject go, List<string> handlers)
        {
            if (go.GetComponent<Button>() != null)        AddUnique(handlers, "onClick");
            if (go.GetComponent<Toggle>() != null)        AddUnique(handlers, "onValueChanged");
            if (go.GetComponent<Slider>() != null)        AddUnique(handlers, "onValueChanged");
            if (go.GetComponent<Scrollbar>() != null)     AddUnique(handlers, "onValueChanged");
            if (go.GetComponent<ScrollRect>() != null)    AddUnique(handlers, "onValueChanged");
            if (go.GetComponent<Dropdown>() != null)      AddUnique(handlers, "onValueChanged");
            if (go.GetComponent<TMP_Dropdown>() != null)  AddUnique(handlers, "onValueChanged");

            if (go.GetComponent<InputField>() != null)
            {
                AddUnique(handlers, "onValueChanged");
                AddUnique(handlers, "onEndEdit");
            }
            if (go.GetComponent<TMP_InputField>() != null)
            {
                AddUnique(handlers, "onValueChanged");
                AddUnique(handlers, "onEndEdit");
                AddUnique(handlers, "onSubmit");
                AddUnique(handlers, "onSelect");
                AddUnique(handlers, "onDeselect");
            }

            // EventTrigger lists its own configured trigger types.
            var trigger = go.GetComponent<EventTrigger>();
            if (trigger != null && trigger.triggers != null)
            {
                foreach (var entry in trigger.triggers)
                    if (entry != null)
                        AddUnique(handlers, entry.eventID.ToString());
            }

            // Custom MonoBehaviours implementing EventSystems handler interfaces.
            foreach (var mb in go.GetComponents<MonoBehaviour>())
            {
                if (mb == null) continue;
                if (mb is IPointerClickHandler) AddUnique(handlers, "IPointerClickHandler");
                if (mb is IPointerDownHandler)  AddUnique(handlers, "IPointerDownHandler");
                if (mb is IPointerUpHandler)    AddUnique(handlers, "IPointerUpHandler");
                if (mb is IDragHandler)         AddUnique(handlers, "IDragHandler");
                if (mb is IDropHandler)         AddUnique(handlers, "IDropHandler");
                if (mb is ISubmitHandler)       AddUnique(handlers, "ISubmitHandler");
            }
        }

        // Split MonoBehaviours into project/AI scripts (custom_scripts) and the
        // interactive UI widgets present on the node (attached_components).
        static void CollectComponents(GameObject go, List<string> custom, List<string> attached)
        {
            foreach (var mb in go.GetComponents<MonoBehaviour>())
            {
                if (mb == null) continue;
                var type = mb.GetType();
                string name = type.Name;

                if (IsInteractiveWidget(mb))
                {
                    AddUnique(attached, name);
                    continue;
                }

                string ns = type.Namespace ?? "";
                bool engineOwned =
                    ns.StartsWith("UnityEngine", StringComparison.Ordinal) ||
                    ns.StartsWith("TMPro", StringComparison.Ordinal) ||
                    ns.StartsWith("AutoAgent", StringComparison.Ordinal);
                if (!engineOwned)
                    AddUnique(custom, name);
            }
        }

        static bool IsInteractiveWidget(MonoBehaviour mb)
        {
            return mb is Selectable
                || mb is ScrollRect
                || mb is TMP_InputField
                || mb is TMP_Dropdown;
        }

        static void AddUnique(List<string> list, string value)
        {
            if (!string.IsNullOrEmpty(value) && !list.Contains(value))
                list.Add(value);
        }

        // ---- meta ----------------------------------------------------------

        static MetaData BuildMeta(Transform t)
        {
            if (!t.TryGetComponent<StableIdComponent>(out var sid))
                return null;

            var m = new MetaData();

            if (sid.logicalRole != AutoAgentLogicalRole.None)
                m.LogicalRole = RoleToString(sid.logicalRole);

            if (!string.IsNullOrEmpty(sid.intent))
                m.Intent = sid.intent;

            if (sid.tags != null && sid.tags.Count > 0)
            {
                var tags = new List<string>();
                foreach (var tag in sid.tags)
                    if (!string.IsNullOrEmpty(tag) && !tags.Contains(tag))
                        tags.Add(tag);
                if (tags.Count > 0)
                    m.Tags = tags;
            }

            if (sid.stateSprites != null && sid.stateSprites.Count > 0)
            {
                m.StateSprites = new Dictionary<string, string>();
                foreach (var p in sid.stateSprites)
                    if (!string.IsNullOrEmpty(p.state))
                        m.StateSprites[p.state] = p.spritePath ?? "";
            }

            return (m.LogicalRole != null || m.Intent != null ||
                    m.Tags != null || m.StateSprites != null) ? m : null;
        }

        static string RoleToString(AutoAgentLogicalRole r) => r switch
        {
            AutoAgentLogicalRole.DragSource      => "drag_source",
            AutoAgentLogicalRole.DropTarget      => "drop_target",
            AutoAgentLogicalRole.Button          => "button",
            AutoAgentLogicalRole.Input           => "input",
            AutoAgentLogicalRole.Slider          => "slider",
            AutoAgentLogicalRole.Toggle          => "toggle",
            AutoAgentLogicalRole.Checkbox        => "checkbox",
            AutoAgentLogicalRole.Dropdown        => "dropdown",
            AutoAgentLogicalRole.Combobox        => "combobox",
            AutoAgentLogicalRole.ScrollContainer => "scroll_container",
            AutoAgentLogicalRole.ListView        => "list_view",
            AutoAgentLogicalRole.TextDisplay     => "text_display",
            AutoAgentLogicalRole.ImageOnly       => "image_only",
            _                                    => null,
        };
    }
}
