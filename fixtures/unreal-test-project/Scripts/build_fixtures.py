"""AutoAgent Phase 0 — UE Editor Python builder.

Usage inside Unreal Editor (after the AutoAgentTest C++ module has been
compiled and the editor reopened):

    Window > Output Log > switch input dropdown to "Python"
    > exec(open(r"D:/AutoAgent/fixtures/unreal-test-project/Scripts/build_fixtures.py").read())

Or:

    Tools > Execute Python Script... > select this file

What it does:
1. Imports every PNG under Content/UI/Sprites/ as Texture2D + UI_BASE.
2. Creates WBP_LoginScreen (parent ULoginUserWidget) and WBP_PocPlayground
   (parent UPocPlaygroundUserWidget) under Content/UI/.
3. Best-effort populates each WBP's WidgetTree with the canonical visual
   skeleton (CanvasPanel + UImage/UTextBlock children).
4. Creates LoginMap and PocPlaygroundMap under Content/Maps/ that boot the
   matching WBP via a small Level Blueprint snippet (user wires it manually
   if Python can't set Level Blueprint code; see DOC printed at the end).

Existing stub .uasset / .umap files are overwritten.
"""

import os
import unreal

UI_DIR = "/Game/UI"
SPRITES_DIR = "/Game/UI/Sprites"
MAPS_DIR = "/Game/Maps"
SOURCE_PNG_DIR = unreal.SystemLibrary.get_project_directory() + "Content/UI/Sprites"

LOGIN_CLASS_PATH = "/Script/AutoAgentTest.LoginUserWidget"
POC_CLASS_PATH = "/Script/AutoAgentTest.PocPlaygroundUserWidget"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
editor_asset = unreal.EditorAssetLibrary
level_lib = unreal.EditorLevelLibrary


def remove_repo_stubs() -> None:
    """Delete the small placeholder .uasset/.umap files committed to the repo."""
    project_dir = unreal.SystemLibrary.get_project_directory()
    stubs = [
        "Content/UI/WBP_LoginScreen.uasset",
        "Content/UI/WBP_PocPlayground.uasset",
        "Content/Maps/LoginMap.umap",
        "Content/Maps/PocPlaygroundMap.umap",
    ]
    for rel in stubs:
        path = os.path.join(project_dir, rel)
        if not os.path.exists(path):
            continue
        if os.path.getsize(path) < 4096:
            try:
                os.remove(path)
                unreal.log(f"[AutoAgent] removed stub {rel}")
            except OSError as exc:
                unreal.log_warning(f"[AutoAgent] could not remove stub {rel}: {exc}")


def ensure_dir(path: str) -> None:
    if not editor_asset.does_directory_exist(path):
        editor_asset.make_directory(path)


def import_sprites() -> dict:
    """Import every PNG under Content/UI/Sprites as Texture2D. Returns dict[name]=Texture2D."""
    ensure_dir(SPRITES_DIR)
    imported: dict = {}
    if not os.path.isdir(SOURCE_PNG_DIR):
        unreal.log_warning(f"[AutoAgent] sprite source dir missing: {SOURCE_PNG_DIR}")
        return imported
    for fn in sorted(os.listdir(SOURCE_PNG_DIR)):
        if not fn.lower().endswith(".png"):
            continue
        name = os.path.splitext(fn)[0]
        asset_path = f"{SPRITES_DIR}/{name}"
        if editor_asset.does_asset_exist(asset_path):
            tex = editor_asset.load_asset(asset_path)
        else:
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
            unreal.log_warning(f"[AutoAgent] failed to import {fn}")
            continue
        # set to UI usage
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_UI)
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_EDITOR_ICON)
        editor_asset.save_loaded_asset(tex)
        imported[name] = tex
    return imported


def delete_if_exists(asset_path: str) -> None:
    if editor_asset.does_asset_exist(asset_path):
        editor_asset.delete_asset(asset_path)


def make_widget_blueprint(name: str, parent_class_path: str) -> unreal.WidgetBlueprint:
    asset_path = f"{UI_DIR}/{name}"
    delete_if_exists(asset_path)
    factory = unreal.WidgetBlueprintFactory()
    parent_class = unreal.load_class(None, parent_class_path)
    if parent_class is None:
        unreal.log_error(
            f"[AutoAgent] Cannot find C++ class {parent_class_path}. "
            "Did you compile the AutoAgentTest module? "
            "Build the editor target then rerun."
        )
        return None
    factory.set_editor_property("parent_class", parent_class)
    wb = asset_tools.create_asset(name, UI_DIR, unreal.WidgetBlueprint, factory)
    return wb


def make_image(tree: unreal.WidgetTree, name: str, texture) -> unreal.Image:
    img = tree.construct_widget(unreal.Image, name)
    if texture is not None:
        brush = unreal.SlateBrush()
        brush.set_editor_property("resource_object", texture)
        brush.set_editor_property("image_size", unreal.Vector2D(texture.blueprint_get_size_x(), texture.blueprint_get_size_y()))
        img.set_editor_property("brush", brush)
    return img


def make_text(tree: unreal.WidgetTree, name: str, content: str) -> unreal.TextBlock:
    t = tree.construct_widget(unreal.TextBlock, name)
    t.set_text(unreal.Text(content))
    return t


def slot_canvas(parent: unreal.CanvasPanel, child, x: float, y: float, w: float, h: float, anchor_center: bool = True):
    slot: unreal.CanvasPanelSlot = parent.add_child_to_canvas_panel(child)
    if anchor_center:
        slot.set_anchors(unreal.Anchors(0.5, 0.5, 0.5, 0.5))
        slot.set_alignment(unreal.Vector2D(0.5, 0.5))
    else:
        slot.set_anchors(unreal.Anchors(0, 0, 0, 0))
    slot.set_position(unreal.Vector2D(x, y))
    slot.set_size(unreal.Vector2D(w, h))
    return slot


def populate_login(wb: unreal.WidgetBlueprint, sprites: dict) -> None:
    tree: unreal.WidgetTree = wb.get_editor_property("widget_tree")
    root = tree.construct_widget(unreal.CanvasPanel, "RootCanvas")
    tree.set_editor_property("root_widget", root)

    # login_panel centered (anchor center)
    panel = make_image(tree, "LoginPanel", sprites.get("panel_bg"))
    slot_canvas(root, panel, 0, 0, 640, 480)

    panel_canvas = tree.construct_widget(unreal.CanvasPanel, "LoginPanelInner")
    # we need a canvas inside login_panel to place children; do that by wrapping
    # via SizeBox isn't trivial — instead put children directly on root_canvas
    # offset by panel center.
    # To keep things simple, place all sub-widgets on root_canvas with the
    # panel's global anchor as reference.

    def child(name: str, sprite_name: str, x: float, y: float, w: float, h: float, is_text=False, text=""):
        if is_text:
            widget = make_text(tree, name, text)
        else:
            widget = make_image(tree, name, sprites.get(sprite_name))
        slot_canvas(root, widget, x, y, w, h)
        return widget

    child("AccountInputBg", "input_bg_normal", 0, -120, 360, 56)
    child("AccountInputText", "", 0, -120, 360, 56, is_text=True, text="")
    child("PasswordInputBg", "input_bg_normal", 0, -40, 360, 56)
    child("PasswordInputText", "", 0, -40, 360, 56, is_text=True, text="")
    child("LoginButtonBg", "btn_login_normal", 0, 60, 240, 64)
    child("LoginButtonLabel", "", 0, 60, 240, 64, is_text=True, text="Login")
    child("ErrorLabel", "", 0, 140, 480, 28, is_text=True, text="")

    welcome = make_image(tree, "WelcomePanel", sprites.get("panel_bg"))
    slot_canvas(root, welcome, 0, 0, 640, 480)
    welcome.set_visibility(unreal.SlateVisibility.HIDDEN)
    welcome_text = make_text(tree, "WelcomeText", "Welcome")
    slot_canvas(root, welcome_text, 0, 0, 640, 480)

    compile_and_save(wb)


def populate_poc(wb: unreal.WidgetBlueprint, sprites: dict) -> None:
    tree: unreal.WidgetTree = wb.get_editor_property("widget_tree")
    root = tree.construct_widget(unreal.CanvasPanel, "RootCanvas")
    tree.set_editor_property("root_widget", root)

    for i, x in enumerate([100, 240, 380, 520, 660, 800]):
        name = "ClickTarget" if i == 0 else f"ClickTargetVariant{i}"
        widget = make_image(tree, name, sprites.get("slot_bg"))
        slot_canvas(root, widget, x, 100, 120, 80, anchor_center=False)

    tt = make_image(tree, "TextTarget", sprites.get("input_bg_normal"))
    slot_canvas(root, tt, 100, 220, 360, 56, anchor_center=False)
    tt_text = make_text(tree, "TextTargetText", "")
    slot_canvas(root, tt_text, 112, 236, 336, 24, anchor_center=False)

    ds = make_image(tree, "DragSource", sprites.get("slot_bg"))
    slot_canvas(root, ds, 100, 320, 100, 100, anchor_center=False)
    dt = make_image(tree, "DragTarget", sprites.get("slot_bg"))
    slot_canvas(root, dt, 260, 320, 100, 100, anchor_center=False)

    sc = make_image(tree, "ScrollContainer", sprites.get("panel_bg"))
    slot_canvas(root, sc, 100, 460, 640, 500, anchor_center=False)

    # scroll_content is a UCanvasPanel placed inside scroll_container's bounds.
    # Since UImage cannot host children, we put scroll_content directly on root
    # but visually overlapping the scroll_container — the adapter understands
    # this via the metadata mapping.
    content = tree.construct_widget(unreal.CanvasPanel, "ScrollContent")
    slot_canvas(root, content, 110, 470, 620, 480, anchor_center=False)

    item_h = 72
    spacing = 8
    for i in range(1, 31):
        item = make_image(tree, f"ScrollItem{i:03d}", sprites.get("slot_bg"))
        cslot: unreal.CanvasPanelSlot = content.add_child_to_canvas_panel(item)
        cslot.set_anchors(unreal.Anchors(0, 0, 0, 0))
        cslot.set_position(unreal.Vector2D(0, (i - 1) * (item_h + spacing)))
        cslot.set_size(unreal.Vector2D(620, item_h))

    compile_and_save(wb)


def compile_and_save(wb: unreal.WidgetBlueprint) -> None:
    unreal.SystemLibrary.execute_console_command(None, "")  # no-op, ensures editor flush
    unreal.EditorAssetLibrary.save_loaded_asset(wb)


def make_map(name: str) -> None:
    asset_path = f"{MAPS_DIR}/{name}"
    delete_if_exists(asset_path)
    ensure_dir(MAPS_DIR)
    new_world = level_lib.new_level(asset_path)
    if new_world is None:
        unreal.log_warning(f"[AutoAgent] could not create level {asset_path}")
        return
    editor_asset.save_asset(asset_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run() -> None:
    unreal.log("[AutoAgent] removing repo stubs...")
    remove_repo_stubs()
    unreal.log("[AutoAgent] importing sprites...")
    sprites = import_sprites()
    unreal.log(f"[AutoAgent] imported {len(sprites)} sprites: {sorted(sprites)}")

    unreal.log("[AutoAgent] creating WBP_LoginScreen...")
    wb_login = make_widget_blueprint("WBP_LoginScreen", LOGIN_CLASS_PATH)
    if wb_login is not None:
        populate_login(wb_login, sprites)

    unreal.log("[AutoAgent] creating WBP_PocPlayground...")
    wb_poc = make_widget_blueprint("WBP_PocPlayground", POC_CLASS_PATH)
    if wb_poc is not None:
        populate_poc(wb_poc, sprites)

    unreal.log("[AutoAgent] creating maps...")
    make_map("LoginMap")
    make_map("PocPlaygroundMap")

    unreal.log("\n[AutoAgent] DONE.\n"
               "Manual follow-up (one-time):\n"
               " 1. Open Content/Maps/LoginMap. In the Level Blueprint's BeginPlay,\n"
               "    'Create Widget' -> WBP_LoginScreen -> 'Add to Viewport'.\n"
               " 2. Same for PocPlaygroundMap -> WBP_PocPlayground.\n"
               " 3. Open each WBP and confirm BindWidget names match the C++ fields\n"
               "    (UMG editor shows green checkmarks). The Python builder uses the\n"
               "    canonical names so this should already be the case.\n")


run()
