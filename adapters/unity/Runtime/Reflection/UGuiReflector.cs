using System.Collections.Generic;
using UnityEngine;
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
            foreach (var root in roots)
                DumpTransform(root.transform, null, nodes);
            return nodes;
        }

        // Returns the stable ID assigned to this transform, or null if it has no RectTransform.
        static string DumpTransform(Transform t, string parentId, List<NodeData> nodes)
        {
            if (!t.TryGetComponent<RectTransform>(out var rt))
                return null;

            string myId = ResolveId(t, out string idSource);

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
                string childId = DumpTransform(child, myId, nodes);
                if (childId != null)
                    node.ChildrenIds.Add(childId);
            }
            return myId;
        }

        static string ResolveId(Transform t, out string source)
        {
            if (t.TryGetComponent<StableIdComponent>(out var sid) &&
                !string.IsNullOrEmpty(sid.pinnedId))
            {
                source = "pinned";
                return sid.pinnedId;
            }
            source = "auto";
            return t.gameObject.name;
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

        static VisualData BuildVisual(RectTransform rt, GameObject go)
        {
            var corners = new Vector3[4];
            rt.GetWorldCorners(corners);
            // corners: [0]=BL [1]=TL [2]=TR [3]=BR
            float xMin = corners[0].x, yMin = corners[0].y;
            float xMax = corners[2].x, yMax = corners[2].y;

            var v = new VisualData
            {
                Position = new[] { rt.anchoredPosition.x, rt.anchoredPosition.y },
                Size     = new[] { rt.rect.width, rt.rect.height },
                Visible  = go.activeInHierarchy,
                WorldBounds = new[] { xMin, yMin, xMax, yMax },
            };

            // Alpha from CanvasGroup if present
            var cg = go.GetComponent<CanvasGroup>();
            if (cg != null) v.Alpha = cg.alpha;

            // Color + sprite from Image
            var img = go.GetComponent<Image>();
            if (img != null)
            {
                var c = img.color;
                v.Color = string.Format("#{0:X2}{1:X2}{2:X2}{3:X2}",
                    (int)(c.r * 255), (int)(c.g * 255),
                    (int)(c.b * 255), (int)(c.a * 255));
                if (img.sprite != null) v.SpriteRef = img.sprite.name;
            }

            return v;
        }

        static BehaviorData BuildBehavior(GameObject go)
        {
            var b = new BehaviorData();
            var selectable = go.GetComponent<Selectable>();
            if (selectable != null)
            {
                b.Interactable = selectable.interactable;
            }
            var graphic = go.GetComponent<Graphic>();
            if (graphic != null)
            {
                b.RaycastTarget = graphic.raycastTarget;
            }
            return (b.Interactable.HasValue || b.RaycastTarget.HasValue) ? b : null;
        }

        static MetaData BuildMeta(Transform t)
        {
            if (!t.TryGetComponent<StableIdComponent>(out var sid))
                return null;

            var m = new MetaData();

            if (sid.logicalRole != AutoAgentLogicalRole.None)
                m.LogicalRole = RoleToString(sid.logicalRole);

            if (sid.stateSprites != null && sid.stateSprites.Count > 0)
            {
                m.StateSprites = new Dictionary<string, string>();
                foreach (var p in sid.stateSprites)
                    if (!string.IsNullOrEmpty(p.state))
                        m.StateSprites[p.state] = p.spritePath ?? "";
            }

            return (m.LogicalRole != null || m.StateSprites != null) ? m : null;
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
