#if UNITY_EDITOR
// AutoAgent Phase 0 — TASK-0008b metadata builder.
//
// Open this project in Unity and run:
//   Tools > AutoAgent > Apply LoginScene Metadata
//
// Attaches StableIdComponent (from the com.autoagent.runtime package) to every
// key node of LoginScene.unity and fills pinnedId / logicalRole / stateSprites.
// Idempotent — safe to re-run after rebuilding the scene.

using System.Collections.Generic;
using AutoAgent;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

public static class AutoAgentMetadataBuilder
{
    const string ScenesRoot = "Assets/Scenes";

    [MenuItem("Tools/AutoAgent/Apply LoginScene Metadata")]
    public static void ApplyLoginSceneMetadata()
    {
        var scene = EditorSceneManager.OpenScene($"{ScenesRoot}/LoginScene.unity", OpenSceneMode.Single);

        Apply(scene, "login_panel",         AutoAgentLogicalRole.ImageOnly);
        Apply(scene, "account_input_bg",    AutoAgentLogicalRole.Input,
              ("normal", "input_bg_normal"), ("focused", "input_bg_focused"));
        Apply(scene, "account_input_text",  AutoAgentLogicalRole.TextDisplay);
        Apply(scene, "password_input_bg",   AutoAgentLogicalRole.Input,
              ("normal", "input_bg_normal"), ("focused", "input_bg_focused"));
        Apply(scene, "password_input_text", AutoAgentLogicalRole.TextDisplay);
        Apply(scene, "login_button_bg",     AutoAgentLogicalRole.Button,
              ("normal", "btn_login_normal"), ("hover", "btn_login_hover"),
              ("pressed", "btn_login_pressed"), ("disabled", "btn_login_disabled"));
        Apply(scene, "login_button_label",  AutoAgentLogicalRole.TextDisplay);
        Apply(scene, "error_label",         AutoAgentLogicalRole.TextDisplay);
        Apply(scene, "welcome_panel",       AutoAgentLogicalRole.ImageOnly);
        Apply(scene, "welcome_text",        AutoAgentLogicalRole.TextDisplay);

        EditorSceneManager.MarkSceneDirty(scene);
        EditorSceneManager.SaveScene(scene);
        AssetDatabase.SaveAssets();
        Debug.Log("[AutoAgent] LoginScene metadata applied (10 nodes).");
    }

    // -----------------------------------------------------------------------

    static void Apply(Scene scene, string nodeName, AutoAgentLogicalRole role,
                      params (string state, string sprite)[] stateSprites)
    {
        var go = FindInScene(scene, nodeName);
        if (go == null)
        {
            Debug.LogWarning($"[AutoAgent] node not found, skipped: {nodeName}");
            return;
        }

        var sid = go.GetComponent<StableIdComponent>();
        if (sid == null) sid = go.AddComponent<StableIdComponent>();

        sid.pinnedId = nodeName;
        sid.logicalRole = role;
        sid.stateSprites = new List<StateSpritePair>();
        foreach (var (state, sprite) in stateSprites)
            sid.stateSprites.Add(new StateSpritePair { state = state, spritePath = sprite });

        EditorUtility.SetDirty(go);
    }

    static GameObject FindInScene(Scene scene, string name)
    {
        foreach (var root in scene.GetRootGameObjects())
        {
            var found = FindRecursive(root.transform, name);
            if (found != null) return found.gameObject;
        }
        return null;
    }

    // Recursive search that includes inactive GameObjects (welcome_panel is hidden).
    static Transform FindRecursive(Transform t, string name)
    {
        if (t.name == name) return t;
        foreach (Transform child in t)
        {
            var found = FindRecursive(child, name);
            if (found != null) return found;
        }
        return null;
    }
}
#endif
