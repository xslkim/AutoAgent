"""AutoAgent Phase 0 - UE Editor Python builder (simplified).

What this DOES (reliable, no UE Python WidgetTree gymnastics):
  1. Delete the small placeholder .uasset/.umap stubs committed to the repo.
  2. Import every PNG under Content/UI/Sprites/ as Texture2D (UI group).
  3. Create empty WBP_LoginScreen / WBP_PocPlayground parented to the C++
     classes ULoginUserWidget / UPocPlaygroundUserWidget.
  4. Create empty LoginMap.umap / PocPlaygroundMap.umap.

What this DOES NOT do (would be flaky; left as manual steps):
  - Populate WidgetTree of the WBPs (drag widgets, set names, assign brushes).
  - Wire Level Blueprint -> Add To Viewport in each Map.
  - Set Project Settings > Maps & Modes default map.

Usage in UE Editor:
  Window > Output Log > switch input dropdown to "Python", then run:
      exec(open(r"D:/AutoAgent/fixtures/unreal-test-project/Scripts/build_fixtures.py").read())
"""

import os
import unreal

UI_DIR = "/Game/UI"
SPRITES_DIR = "/Game/UI/Sprites"
MAPS_DIR = "/Game/Maps"
SOURCE_PNG_DIR = unreal.SystemLibrary.get_project_directory() + "Content/UI/Sprites"
LOGIN_CLASS_PATH = "/Script/AutoAgentTest.LoginUserWidget"
POC_CLASS_PATH = "/Script/AutoAgentTest.PocPlaygroundUserWidget"

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
editor_asset = unreal.EditorAssetLibrary
level_lib = unreal.EditorLevelLibrary


def remove_repo_stubs():
    project_dir = unreal.SystemLibrary.get_project_directory()
    for rel in (
        "Content/UI/WBP_LoginScreen.uasset",
        "Content/UI/WBP_PocPlayground.uasset",
        "Content/Maps/LoginMap.umap",
        "Content/Maps/PocPlaygroundMap.umap",
    ):
        path = os.path.join(project_dir, rel)
        if os.path.exists(path) and os.path.getsize(path) < 4096:
            try:
                os.remove(path)
                unreal.log("[AutoAgent] removed stub %s" % rel)
            except OSError as exc:
                unreal.log_warning("[AutoAgent] could not remove %s: %s" % (rel, exc))


def import_sprites():
    if not editor_asset.does_directory_exist(SPRITES_DIR):
        editor_asset.make_directory(SPRITES_DIR)
    if not os.path.isdir(SOURCE_PNG_DIR):
        unreal.log_warning("[AutoAgent] sprite source missing: %s" % SOURCE_PNG_DIR)
        return {}
    imported = {}
    for fn in sorted(os.listdir(SOURCE_PNG_DIR)):
        if not fn.lower().endswith(".png"):
            continue
        name = os.path.splitext(fn)[0]
        asset_path = "%s/%s" % (SPRITES_DIR, name)
        if not editor_asset.does_asset_exist(asset_path):
            task = unreal.AssetImportTask()
            task.filename = os.path.join(SOURCE_PNG_DIR, fn)
            task.destination_path = SPRITES_DIR
            task.destination_name = name
            task.automated = True
            task.replace_existing = True
            task.save = True
            asset_tools.import_asset_tasks([task])
        tex = editor_asset.load_asset(asset_path)
        if tex is None:
            unreal.log_warning("[AutoAgent] failed to import %s" % fn)
            continue
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_UI)
        editor_asset.save_loaded_asset(tex)
        imported[name] = tex
    return imported


def delete_if_exists(asset_path):
    if editor_asset.does_asset_exist(asset_path):
        editor_asset.delete_asset(asset_path)


def make_widget_blueprint(name, parent_class_path):
    asset_path = "%s/%s" % (UI_DIR, name)
    delete_if_exists(asset_path)
    if not editor_asset.does_directory_exist(UI_DIR):
        editor_asset.make_directory(UI_DIR)
    parent_class = unreal.load_class(None, parent_class_path)
    if parent_class is None:
        unreal.log_error(
            "[AutoAgent] Cannot find C++ class %s. "
            "Did you compile the AutoAgentTest module? Rebuild then rerun." % parent_class_path
        )
        return None
    factory = unreal.WidgetBlueprintFactory()
    factory.set_editor_property("parent_class", parent_class)
    wb = asset_tools.create_asset(name, UI_DIR, unreal.WidgetBlueprint, factory)
    if wb is not None:
        editor_asset.save_loaded_asset(wb)
        unreal.log("[AutoAgent] created %s (parent=%s)" % (asset_path, parent_class_path))
    return wb


def make_map(name):
    asset_path = "%s/%s" % (MAPS_DIR, name)
    delete_if_exists(asset_path)
    if not editor_asset.does_directory_exist(MAPS_DIR):
        editor_asset.make_directory(MAPS_DIR)
    new_world = level_lib.new_level(asset_path)
    if new_world is not None:
        editor_asset.save_asset(asset_path)
        unreal.log("[AutoAgent] created %s" % asset_path)


def run():
    unreal.log("[AutoAgent] removing repo stubs...")
    remove_repo_stubs()
    unreal.log("[AutoAgent] importing sprites...")
    sprites = import_sprites()
    unreal.log("[AutoAgent] imported %d sprites: %s" % (len(sprites), sorted(sprites)))
    make_widget_blueprint("WBP_LoginScreen", LOGIN_CLASS_PATH)
    make_widget_blueprint("WBP_PocPlayground", POC_CLASS_PATH)
    make_map("LoginMap")
    make_map("PocPlaygroundMap")
    unreal.log(
        "\n[AutoAgent] DONE. Manual UMG steps remaining (see docs/10 §6.3/§6.4):\n"
        " 1. Open Content/UI/WBP_LoginScreen in UMG editor.\n"
        "    Add widgets with EXACTLY these names (each: tick 'Is Variable'):\n"
        "      LoginPanel (UImage)        - center, 640x480, Brush=panel_bg\n"
        "      AccountInputBg (UImage)    - 360x56, Brush=input_bg_normal\n"
        "      AccountInputText (UTextBlock, child of AccountInputBg, text='')\n"
        "      PasswordInputBg, PasswordInputText (same as Account)\n"
        "      LoginButtonBg (UImage 240x64, Brush=btn_login_normal)\n"
        "      LoginButtonLabel (UTextBlock child of LoginButtonBg, text='Login')\n"
        "      ErrorLabel (UTextBlock, text='')\n"
        "      WelcomePanel (UImage 640x480, Visibility=Hidden)\n"
        "      WelcomeText (UTextBlock child of WelcomePanel, text='Welcome')\n"
        " 2. Open Content/UI/WBP_PocPlayground in UMG editor. See docs/10 §6.4.\n"
        " 3. Open Content/Maps/LoginMap -> Level Blueprint -> BeginPlay:\n"
        "    Create Widget(WBP_LoginScreen) -> Add to Viewport.\n"
        " 4. Same for PocPlaygroundMap -> WBP_PocPlayground.\n"
        " 5. Edit > Project Settings > Maps & Modes -> Default Maps:\n"
        "    Editor Startup Map = LoginMap, Game Default Map = LoginMap.\n"
    )


run()
