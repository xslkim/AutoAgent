using System.Collections.Generic;
using System.Text.RegularExpressions;
using NUnit.Framework;

namespace AutoAgent.Tests
{
    /// <summary>
    /// Tests for NodeSerializer — the hand-rolled NodeData → wire JSON writer.
    /// Plain [Test] methods: run in both EditMode and PlayMode test runners.
    /// </summary>
    public class NodeSerializerTests
    {
        // A node with every field populated — mirrors what a fully-reflected
        // interactive widget (Button + Image) looks like.
        static NodeData FullNode()
        {
            return new NodeData
            {
                Id = "login_button",
                Type = "Button",
                EngineType = "UnityEngine.UI.Button",
                ParentId = "login_panel",
                ChildrenIds = new List<string> { "login_label" },
                StableIdSource = "pinned",
                Visual = new VisualData
                {
                    Position = new[] { 12.5f, -40f },
                    Size = new[] { 200f, 60f },
                    Anchor = new[] { 0.5f, 0.5f },
                    Visible = true,
                    Alpha = 1f,
                    Color = "#3366CCFF",
                    SpriteRef = "btn_normal",
                    WorldBounds = new[] { 0f, 0f, 200f, 60f },
                    ZOrder = 3f,
                },
                Behavior = new BehaviorData
                {
                    Interactable = true,
                    RaycastTarget = true,
                    EventHandlers = new List<string> { "onClick" },
                    CustomScripts = new List<string>(),
                    AttachedComponents = new List<string> { "Button" },
                },
                Meta = new MetaData
                {
                    LogicalRole = "button",
                    Intent = "submit the login form",
                    Tags = new List<string> { "primary", "auth" },
                    StateSprites = new Dictionary<string, string>
                    {
                        { "normal", "btn_normal" },
                        { "pressed", "btn_pressed" },
                    },
                },
            };
        }

        // ---- structural -----------------------------------------------------

        [Test]
        public void SerializesTreeAsJsonArray()
        {
            string json = NodeSerializer.SerializeTree(new List<NodeData> { FullNode() });
            Assert.IsTrue(json.StartsWith("["), "tree must be a JSON array");
            Assert.IsTrue(json.EndsWith("]"), "tree must be a JSON array");
        }

        [Test]
        public void EmitsAllRequiredTopLevelKeys()
        {
            string json = NodeSerializer.SerializeTree(new List<NodeData> { FullNode() });
            foreach (var key in new[]
            {
                "\"id\"", "\"type\"", "\"engine_type\"", "\"parent_id\"",
                "\"children_ids\"", "\"stable_id_source\"", "\"visual\"",
            })
                StringAssert.Contains(key, json);
        }

        // ---- the six TASK-0100 verification fields --------------------------

        [Test]
        public void EmitsTheSixVerificationFields()
        {
            string json = NodeSerializer.SerializeTree(new List<NodeData> { FullNode() });
            // visible / alpha / color / sprite_ref are in visual
            StringAssert.Contains("\"visible\":true", json);
            StringAssert.Contains("\"alpha\":", json);
            StringAssert.Contains("\"color\":\"#3366CCFF\"", json);
            StringAssert.Contains("\"sprite_ref\":\"btn_normal\"", json);
            // interactable / event_handlers are in behavior
            StringAssert.Contains("\"interactable\":true", json);
            StringAssert.Contains("\"event_handlers\":[\"onClick\"]", json);
        }

        [Test]
        public void ColorMatchesSchemaHexPattern()
        {
            string json = NodeSerializer.SerializeTree(new List<NodeData> { FullNode() });
            var m = Regex.Match(json, "\"color\":\"(#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?)\"");
            Assert.IsTrue(m.Success, "color must be #RRGGBB or #RRGGBBAA");
        }

        [Test]
        public void AlphaIsWithinUnitRange()
        {
            string json = NodeSerializer.SerializeTree(new List<NodeData> { FullNode() });
            var m = Regex.Match(json, "\"alpha\":([0-9.]+)");
            Assert.IsTrue(m.Success, "alpha must be emitted");
            float alpha = float.Parse(m.Groups[1].Value, System.Globalization.CultureInfo.InvariantCulture);
            Assert.GreaterOrEqual(alpha, 0f);
            Assert.LessOrEqual(alpha, 1f);
        }

        // ---- new visual fields ---------------------------------------------

        [Test]
        public void EmitsAnchorAndZOrder()
        {
            string json = NodeSerializer.SerializeTree(new List<NodeData> { FullNode() });
            StringAssert.Contains("\"anchor\":[0.5,0.5]", json);
            StringAssert.Contains("\"z_order\":3", json);
        }

        // ---- new behavior arrays -------------------------------------------

        [Test]
        public void EmitsBehaviorArraysIncludingEmptyOnes()
        {
            string json = NodeSerializer.SerializeTree(new List<NodeData> { FullNode() });
            StringAssert.Contains("\"custom_scripts\":[]", json);
            StringAssert.Contains("\"attached_components\":[\"Button\"]", json);
        }

        // ---- numbers --------------------------------------------------------

        [Test]
        public void NumbersUseInvariantDecimalSeparator()
        {
            // A regression guard: on a zh-CN / de-DE locale a culture-sensitive
            // ToString would emit "12,5" and break JSON parsing.
            string json = NodeSerializer.SerializeTree(new List<NodeData> { FullNode() });
            StringAssert.Contains("\"position\":[12.5,-40]", json);
            Assert.IsFalse(json.Contains("12,5"), "decimal separator must be '.'");
        }

        // ---- escaping -------------------------------------------------------

        [Test]
        public void EscapesSpecialCharactersInStrings()
        {
            var node = FullNode();
            node.Id = "weird\"id\\with\nnewline";
            string json = NodeSerializer.SerializeTree(new List<NodeData> { node });
            StringAssert.Contains("\\\"", json);
            StringAssert.Contains("\\\\", json);
            StringAssert.Contains("\\n", json);
        }

        // ---- parent_id null -------------------------------------------------

        [Test]
        public void RootNodeSerializesNullParentId()
        {
            var node = FullNode();
            node.ParentId = null;
            string json = NodeSerializer.SerializeTree(new List<NodeData> { node });
            StringAssert.Contains("\"parent_id\":null", json);
        }

        // ---- meta -----------------------------------------------------------

        [Test]
        public void EmitsMetaLogicalRoleAndStateSprites()
        {
            string json = NodeSerializer.SerializeTree(new List<NodeData> { FullNode() });
            StringAssert.Contains("\"logical_role\":\"button\"", json);
            StringAssert.Contains("\"state_sprites\":{", json);
            StringAssert.Contains("\"normal\":\"btn_normal\"", json);
        }

        [Test]
        public void EmitsMetaIntentAndTags()
        {
            string json = NodeSerializer.SerializeTree(new List<NodeData> { FullNode() });
            StringAssert.Contains("\"intent\":\"submit the login form\"", json);
            StringAssert.Contains("\"tags\":[\"primary\",\"auth\"]", json);
        }
    }
}
