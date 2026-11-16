"""Build the three-chapter epilogue candidate with an extra alley encounter."""
from build_lantern_city_campaign import assemble_campaign
from build_lantern_city_epilogue import WorkbenchEpilogue
from build_lantern_city_ui import attach_ui
from build_night_market import publish_candidate
from build_tadpole_encounter import TadpoleEncounter
from build_train_station_readability import CONTRAST_STOPS


def assemble_tadpole_campaign(*, contrast_stops=CONTRAST_STOPS, station_sources=None):
    puddle = ("puddle", "puddle.complete", TadpoleEncounter().author)
    campaign, revisions = assemble_campaign(ending=WorkbenchEpilogue, alley_followup=puddle,
                                             contrast_stops=contrast_stops, station_sources=station_sources)
    campaign.source["sections"]["alley.safe_exit"]["hint"] = "摊主已获救。巷口的水洼还在翻动。"
    campaign.source["sections"]["alley.missed_rescue"]["hint"] = "摊主仍被困住。小心巷口水洼里扑过来的墨。"
    attach_ui(campaign)
    return campaign, revisions


def build():
    campaign, revisions = assemble_tadpole_campaign()
    campaign.source["id"] = "paper.lantern_city_tadpole"
    publish_candidate(campaign, revisions)


if __name__ == "__main__":
    build()
