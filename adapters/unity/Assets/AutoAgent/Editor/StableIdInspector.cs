using UnityEditor;
using UnityEngine;

namespace AutoAgent.Editor
{
    /// <summary>
    /// Custom Inspector for <see cref="StableIdComponent"/>.
    ///
    /// Lets a fixture author (artist / programmer) pin a stable id and the
    /// semantic metadata the AutoAgent wire protocol exposes — Pin ID, Role,
    /// Intent, Tags, State Sprites — straight from the Unity Inspector. Edits
    /// are written back through SerializedProperty so they persist on the
    /// component's SerializeFields and survive domain reload / scene save.
    /// </summary>
    [CustomEditor(typeof(StableIdComponent))]
    [CanEditMultipleObjects]
    public class StableIdInspector : UnityEditor.Editor
    {
        SerializedProperty _pinnedId;
        SerializedProperty _logicalRole;
        SerializedProperty _intent;
        SerializedProperty _tags;
        SerializedProperty _stateSprites;

        void OnEnable()
        {
            _pinnedId = serializedObject.FindProperty("pinnedId");
            _logicalRole = serializedObject.FindProperty("logicalRole");
            _intent = serializedObject.FindProperty("intent");
            _tags = serializedObject.FindProperty("tags");
            _stateSprites = serializedObject.FindProperty("stateSprites");
        }

        public override void OnInspectorGUI()
        {
            serializedObject.Update();

            EditorGUILayout.LabelField("AutoAgent Stable ID", EditorStyles.boldLabel);

            EditorGUILayout.PropertyField(_pinnedId,
                new GUIContent("Pin ID", "Stable identifier referenced by task DSL. "
                    + "Leave empty to fall back to an auto-generated hash id."));
            EditorGUILayout.PropertyField(_logicalRole,
                new GUIContent("Role", "Semantic role — maps to protocol meta.logical_role."));
            EditorGUILayout.PropertyField(_intent,
                new GUIContent("Intent", "Free-form description of what this widget is for."));
            EditorGUILayout.PropertyField(_tags,
                new GUIContent("Tags", "Arbitrary classification tags."), true);
            EditorGUILayout.PropertyField(_stateSprites,
                new GUIContent("State Sprites", "State → sprite-path pairs."), true);

            if (string.IsNullOrWhiteSpace(_pinnedId.stringValue))
            {
                EditorGUILayout.HelpBox(
                    "No Pin ID set — this node will receive an auto hash id, "
                    + "which is not referenceable from task DSL.",
                    MessageType.Info);
            }

            serializedObject.ApplyModifiedProperties();
        }
    }
}
