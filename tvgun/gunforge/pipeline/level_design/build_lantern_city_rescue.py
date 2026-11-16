"""Build the full route with the water encounter and Passerby A rescue."""
from build_lantern_city_tadpole import assemble_tadpole_campaign
from build_night_market import publish_candidate
from build_platform_passerby import PlatformPasserby
from build_train_station_readability import CONTRAST_STOPS


def assemble_rescue_campaign(*, station_sources=None):
    stops = tuple(PlatformPasserby if stop.stage == "platform" else stop for stop in CONTRAST_STOPS)
    return assemble_tadpole_campaign(contrast_stops=stops, station_sources=station_sources)


def build():
    campaign, revisions = assemble_rescue_campaign()
    campaign.source["id"] = "paper.lantern_city_rescue"
    publish_candidate(campaign, revisions)


if __name__ == "__main__":
    build()
