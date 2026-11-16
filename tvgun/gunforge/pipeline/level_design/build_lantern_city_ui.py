"""Try the T08 paper HUD and result art across all three campaign chapters."""
import hashlib

from build_lantern_city_campaign import assemble_campaign
from build_night_market import publish_candidate
from build_train_stop import GAME
from compiler import ROOT
from schema_contract import hud_images


def attach_ui(campaign):
    ui = GAME / "assets/stations/g01_st_l1_01_alley/ui"
    layout = GAME / "assets/ui/hud_layout.json"
    files = {"layout": layout, "style": ui / "ui.json", **{name: ui / f"{name}.png" for name in hud_images}}
    lettering = GAME / "reports/art/T09/generation"
    files.update(title=lettering / "game_title_1_v2.png", night_market=lettering / "night_market_1_v2.png",
                 cinema=lettering / "old_cinema_1_v2.png", train_station=lettering / "railway_station_1_v2.png")
    ids = {name: f"hud.{name}" for name in files}
    for name, path in files.items():
        campaign.source["resources"][ids[name]] = {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "kind": "metadata" if path.suffix == ".json" else "image",
        }
    campaign.presentation["hud_art"] = {"layout": ids["layout"], "style": ids["style"],
                                         "images": {name: ids[name] for name in hud_images},
                                         "lettering": {"title": ids["title"], "first_chapter": ids["night_market"],
                                                       "chapters": {"story.cinema_intro": ids["cinema"],
                                                                    "story.train_station_intro": ids["train_station"]}}}


def build():
    campaign, revisions = assemble_campaign()
    campaign.source["id"] = "paper.lantern_city_ui"
    attach_ui(campaign)
    publish_candidate(campaign, revisions)


if __name__ == "__main__":
    build()
