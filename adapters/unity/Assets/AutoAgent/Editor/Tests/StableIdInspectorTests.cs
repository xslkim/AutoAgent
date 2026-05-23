using NUnit.Framework;
using UnityEditor;
using UnityEngine;
using AutoAgent.Editor;

namespace AutoAgent.Editor.Tests
{
    /// <summary>
    /// EditMode tests for StableIdInspector — verifies the custom Inspector
    /// targets StableIdComponent and that its fields persist through
    /// SerializedObject (the path the Inspector writes edits back through).
    /// </summary>
    public class StableIdInspectorTests
    {
        GameObject _go;

        [SetUp]
        public void SetUp()
        {
            _go = new GameObject("InspectorTestTarget");
        }

        [TearDown]
        public void TearDown()
        {
            if (_go != null) Object.DestroyImmediate(_go);
        }

        // ---- the inspector binds to the right component --------------------

        [Test]
        public void InspectorTargetsStableIdComponent()
        {
            var attrs = typeof(StableIdInspector)
                .GetCustomAttributes(typeof(CustomEditor), false);
            Assert.IsNotEmpty(attrs, "StableIdInspector must carry a [CustomEditor] attribute");
        }

        [Test]
        public void CreateEditorReturnsStableIdInspector()
        {
            var sid = _go.AddComponent<StableIdComponent>();
            var editor = UnityEditor.Editor.CreateEditor(sid);
            try
            {
                Assert.IsInstanceOf<StableIdInspector>(editor,
                    "Unity must pick StableIdInspector for a StableIdComponent");
            }
            finally
            {
                Object.DestroyImmediate(editor);
            }
        }

        // ---- all expected fields are present + serialized ------------------

        [Test]
        public void ComponentExposesAllInspectorProperties()
        {
            var sid = _go.AddComponent<StableIdComponent>();
            var so = new SerializedObject(sid);
            foreach (var name in new[] { "pinnedId", "logicalRole", "intent", "tags", "stateSprites" })
                Assert.IsNotNull(so.FindProperty(name), $"serialized property '{name}' missing");
        }

        // ---- edits persist through SerializedObject (TASK-0102 verification) ----

        [Test]
        public void EditedFieldsPersistAfterApply()
        {
            var sid = _go.AddComponent<StableIdComponent>();
            var so = new SerializedObject(sid);

            so.FindProperty("pinnedId").stringValue = "login_button";
            so.FindProperty("intent").stringValue = "submit the login form";
            so.FindProperty("logicalRole").enumValueIndex = (int)AutoAgentLogicalRole.Button;

            var tags = so.FindProperty("tags");
            tags.arraySize = 2;
            tags.GetArrayElementAtIndex(0).stringValue = "primary";
            tags.GetArrayElementAtIndex(1).stringValue = "auth";

            so.ApplyModifiedProperties();

            // The edits must be visible on the live component.
            Assert.AreEqual("login_button", sid.pinnedId);
            Assert.AreEqual("submit the login form", sid.intent);
            Assert.AreEqual(AutoAgentLogicalRole.Button, sid.logicalRole);
            Assert.AreEqual(2, sid.tags.Count);
            Assert.AreEqual("primary", sid.tags[0]);
            Assert.AreEqual("auth", sid.tags[1]);
        }

        [Test]
        public void StateSpritePairsPersistThroughSerializedObject()
        {
            var sid = _go.AddComponent<StableIdComponent>();
            var so = new SerializedObject(sid);

            var sprites = so.FindProperty("stateSprites");
            sprites.arraySize = 1;
            var pair = sprites.GetArrayElementAtIndex(0);
            pair.FindPropertyRelative("state").stringValue = "pressed";
            pair.FindPropertyRelative("spritePath").stringValue = "Sprites/btn_pressed";
            so.ApplyModifiedProperties();

            Assert.AreEqual(1, sid.stateSprites.Count);
            Assert.AreEqual("pressed", sid.stateSprites[0].state);
            Assert.AreEqual("Sprites/btn_pressed", sid.stateSprites[0].spritePath);
        }
    }
}
