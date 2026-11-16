"""Build all three Paper Lantern City chapters in one player session."""
from build_night_market import assemble, chapter_intro, publish_candidate
from build_train_station import append_stops
from build_train_station_hardened import attach_eyes
from build_train_station_readability import CONTRAST_STOPS
from build_workbench_ending import WorkbenchEnding


def assemble_campaign(*, ending=WorkbenchEnding, alley_followup=None, contrast_stops=CONTRAST_STOPS,
                      station_sources=None):
    campaign, revisions = assemble(with_cinema=True, continue_after_cinema=True, alley_followup=alley_followup,
                                   station_sources=station_sources)
    campaign.source["id"] = "paper.lantern_city_campaign"
    campaign.presentation.update(subtitle="夜市 · 旧影院 · 火车站",
                                 instructions="点灯净墨 · 救出纸居民 · 找到墨的源头")
    chapter_intro(campaign, "story.train_station_intro", "cinema.screen_stage", "第三关 · 火车站",
                  "沿着灯光穿过车站，去找墨的源头。")
    append_stops(campaign, revisions, (*contrast_stops, ending), configure_stop=attach_eyes, transition_ms=1500)
    return campaign, revisions


def build():
    publish_candidate(*assemble_campaign())


if __name__ == "__main__":
    build()
