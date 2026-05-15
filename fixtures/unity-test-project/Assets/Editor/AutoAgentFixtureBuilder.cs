#if UNITY_EDITOR
// AutoAgent Phase 0 fixture builder.
//
// Open this project in Unity and run:
//   Tools > AutoAgent > Build All Fixtures
//
// Builds Assets/Scenes/LoginScene.unity and Assets/Scenes/PocPlaygroundScene.unity
// from the sprites in Assets/Sprites/UI. Pure visual skeleton — no Button,
// TMP_InputField, ScrollRect, Toggle, Slider, InputField (forbidden by docs/10).

using System.IO;
using TMPro;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public static class AutoAgentFixtureBuilder
{
    const string SpriteRoot = "Assets/Sprites/UI";
    const string FontRoot = "Assets/Fonts";
    const string ScenesRoot = "Assets/Scenes";

    [MenuItem("Tools/AutoAgent/Build All Fixtures")]
    public static void BuildAll()
    {
        Directory.CreateDirectory(ScenesRoot);
        EnsureSpriteImport();
        BuildLoginScene();
        BuildPocPlaygroundScene();
        AssetDatabase.SaveAssets();
        AssetDatabase.Refresh();
        Debug.Log("[AutoAgent] Fixtures built.");
    }

    [MenuItem("Tools/AutoAgent/Build LoginScene")]
    public static void BuildLoginSceneMenu() { EnsureSpriteImport(); BuildLoginScene(); }

    [MenuItem("Tools/AutoAgent/Build PocPlaygroundScene")]
    public static void BuildPocPlaygroundSceneMenu() { EnsureSpriteImport(); BuildPocPlaygroundScene(); }

    // Make sure every UI PNG is imported as a Sprite (not Texture2D).
    static void EnsureSpriteImport()
    {
        foreach (var path in Directory.GetFiles(SpriteRoot, "*.png"))
        {
            var importer = AssetImporter.GetAtPath(path) as TextureImporter;
            if (importer == null) continue;
            bool dirty = false;
            if (importer.textureType != TextureImporterType.Sprite) { importer.textureType = TextureImporterType.Sprite; dirty = true; }
            if (importer.spriteImportMode != SpriteImportMode.Single) { importer.spriteImportMode = SpriteImportMode.Single; dirty = true; }
            if (dirty) importer.SaveAndReimport();
        }
    }

    static Sprite LoadSprite(string name) => AssetDatabase.LoadAssetAtPath<Sprite>($"{SpriteRoot}/{name}");

    // Intentionally not assigning a custom TMP_FontAsset here.
    // Reason: creating one via TMP_FontAsset.CreateFontAsset(font) at edit-time produces a
    // Dynamic-mode SDF whose atlas Texture2D is not persisted as a sub-asset, so reopening
    // the scene throws MissingReferenceException when TMP tries to add glyphs to the atlas.
    // Fixture phase uses TMP's built-in default font; swap to a real Roboto SDF asset only
    // when capturing visual baselines (manually via Window > TextMeshPro > Font Asset Creator).

    // -----------------------------------------------------------------------
    // Login scene
    // -----------------------------------------------------------------------
    public static void BuildLoginScene()
    {
        var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
        var canvas = MakeCanvas();
        MakeEventSystem();

        var panel = MakeImage("login_panel", canvas.transform, Vector2.zero, new Vector2(640, 480), LoadSprite("panel_bg.png"));

        var acctBg = MakeImage("account_input_bg", panel.transform, new Vector2(0, 120), new Vector2(360, 56), LoadSprite("input_bg_normal.png"));
        MakeText("account_input_text", acctBg.transform, "", new Vector2(0, 0), new Vector2(336, 24));

        var pwdBg = MakeImage("password_input_bg", panel.transform, new Vector2(0, 40), new Vector2(360, 56), LoadSprite("input_bg_normal.png"));
        MakeText("password_input_text", pwdBg.transform, "", new Vector2(0, 0), new Vector2(336, 24));

        var btnBg = MakeImage("login_button_bg", panel.transform, new Vector2(0, -60), new Vector2(240, 64), LoadSprite("btn_login_normal.png"));
        MakeText("login_button_label", btnBg.transform, "Login", new Vector2(0, 0), new Vector2(240, 64));

        MakeText("error_label", panel.transform, "", new Vector2(0, -140), new Vector2(480, 28));

        var welcome = MakeImage("welcome_panel", canvas.transform, Vector2.zero, new Vector2(640, 480), LoadSprite("panel_bg.png"));
        welcome.SetActive(false);
        MakeText("welcome_text", welcome.transform, "Welcome", Vector2.zero, new Vector2(640, 480));

        Directory.CreateDirectory(ScenesRoot);
        EditorSceneManager.SaveScene(scene, $"{ScenesRoot}/LoginScene.unity");
    }

    // -----------------------------------------------------------------------
    // PocPlayground scene
    // -----------------------------------------------------------------------
    public static void BuildPocPlaygroundScene()
    {
        var scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
        var canvas = MakeCanvas();
        MakeEventSystem();

        // top row: click_target + 5 variants
        for (int i = 0; i <= 5; i++)
        {
            string name = i == 0 ? "click_target" : $"click_target_variant_{i}";
            float x = -800 + i * 140;
            MakeImage(name, canvas.transform, new Vector2(x, 440), new Vector2(120, 80), LoadSprite("slot_bg.png"));
        }

        var textBg = MakeImage("text_target", canvas.transform, new Vector2(-700, 300), new Vector2(360, 56), LoadSprite("input_bg_normal.png"));
        MakeText("text_target_text", textBg.transform, "", Vector2.zero, new Vector2(336, 24));

        MakeImage("drag_source", canvas.transform, new Vector2(-820, 180), new Vector2(100, 100), LoadSprite("slot_bg.png"));
        MakeImage("drag_target", canvas.transform, new Vector2(-680, 180), new Vector2(100, 100), LoadSprite("slot_bg.png"));

        // scroll_container as Image (no ScrollRect — forbidden)
        var scroll = MakeImage("scroll_container", canvas.transform, new Vector2(-540, -120), new Vector2(640, 500), LoadSprite("panel_bg.png"));
        var contentGo = new GameObject("scroll_content", typeof(RectTransform));
        contentGo.transform.SetParent(scroll.transform, false);
        var contentRt = (RectTransform)contentGo.transform;
        contentRt.anchorMin = new Vector2(0, 1);
        contentRt.anchorMax = new Vector2(0, 1);
        contentRt.pivot = new Vector2(0, 1);
        const int itemH = 72;
        const int spacing = 8;
        const int items = 30;
        contentRt.sizeDelta = new Vector2(620, items * (itemH + spacing));
        contentRt.anchoredPosition = new Vector2(10, -10);
        for (int i = 1; i <= items; i++)
        {
            var item = new GameObject($"scroll_item_{i:D3}", typeof(RectTransform), typeof(Image));
            item.transform.SetParent(contentGo.transform, false);
            var rt = (RectTransform)item.transform;
            rt.anchorMin = new Vector2(0, 1);
            rt.anchorMax = new Vector2(0, 1);
            rt.pivot = new Vector2(0, 1);
            rt.sizeDelta = new Vector2(620, itemH);
            rt.anchoredPosition = new Vector2(0, -(i - 1) * (itemH + spacing));
            var img = item.GetComponent<Image>();
            img.sprite = LoadSprite("slot_bg.png");
            img.raycastTarget = false;
        }

        Directory.CreateDirectory(ScenesRoot);
        EditorSceneManager.SaveScene(scene, $"{ScenesRoot}/PocPlaygroundScene.unity");
    }

    // -----------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------
    static GameObject MakeCanvas()
    {
        var go = new GameObject("Canvas", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
        var c = go.GetComponent<Canvas>();
        c.renderMode = RenderMode.ScreenSpaceOverlay;
        var s = go.GetComponent<CanvasScaler>();
        s.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        s.referenceResolution = new Vector2(1920, 1080);
        s.matchWidthOrHeight = 0.5f;
        return go;
    }

    static void MakeEventSystem()
    {
        new GameObject("EventSystem", typeof(EventSystem), typeof(StandaloneInputModule));
    }

    static GameObject MakeImage(string name, Transform parent, Vector2 anchoredPos, Vector2 size, Sprite sprite)
    {
        var go = new GameObject(name, typeof(RectTransform), typeof(Image));
        go.transform.SetParent(parent, false);
        var rt = (RectTransform)go.transform;
        rt.anchorMin = rt.anchorMax = new Vector2(0.5f, 0.5f);
        rt.pivot = new Vector2(0.5f, 0.5f);
        rt.sizeDelta = size;
        rt.anchoredPosition = anchoredPos;
        var img = go.GetComponent<Image>();
        img.sprite = sprite;
        img.raycastTarget = false;
        return go;
    }

    static GameObject MakeText(string name, Transform parent, string content, Vector2 anchoredPos, Vector2 size)
    {
        var go = new GameObject(name, typeof(RectTransform), typeof(TextMeshProUGUI));
        go.transform.SetParent(parent, false);
        var rt = (RectTransform)go.transform;
        rt.anchorMin = rt.anchorMax = new Vector2(0.5f, 0.5f);
        rt.pivot = new Vector2(0.5f, 0.5f);
        rt.sizeDelta = size;
        rt.anchoredPosition = anchoredPos;
        var t = go.GetComponent<TextMeshProUGUI>();
        t.text = content;
        t.fontSize = 24;
        t.alignment = TextAlignmentOptions.Center;
        t.color = Color.black;
        t.raycastTarget = false;
        return go;
    }
}
#endif
