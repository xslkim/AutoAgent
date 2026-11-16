"""Assemble the four train-station battles and workbench arrival into one session."""
from build_green_car import GreenCar
from build_lantern_pullback import LanternPullback
from build_night_market import TRANSITION_MS, NightMarket, publish_candidate
from build_platform import Platform
from build_waiting_room import WaitingRoom
from versions import publish


STOPS = (WaitingRoom, Platform, GreenCar, LanternPullback)
STATION_TITLES = ("候车室", "站台", "绿皮车厢", "灯座", "爷爷的工作台")


def append_stops(station, revisions, stops, *, configure_stop=None, transition_ms=TRANSITION_MS):
    offset = len(station.presentation["stations"])
    station.presentation["stations"].extend(STATION_TITLES)
    for position, constructor in enumerate(stops, 1):
        index = offset + position
        stop = constructor()
        source = stop.author()
        revisions[source["id"]] = publish(source).parent.name
        if configure_stop is not None:
            configure_stop(stop)
        last = position == len(stops)
        # Keep the intermediate cut in its own renderer section while the workbench is station five.
        indices = dict.fromkeys(source["sections"]) if last else None
        if last:
            indices.update({stop.stage: index, "workbench": index + 1})
            station.presentation["labels"]["result_success"] = source["presentation"]["labels"]["result_success"]
        station.append(stop.stage, index, f"{stop.stage}.complete", source,
                       continue_after=not last, station_indices=indices,
                       transition_ms=transition_ms if position == 1 else TRANSITION_MS)


def build(*, package="paper.train_station", stops=STOPS, configure_stop=None):
    station = NightMarket()
    station.source.update(id=package, seed=434)
    station.presentation.update(subtitle="第三关 · 火车站", instructions="穿过火车站 · 净化灯座 · 抵达工作台",
                                stations=[])
    station.presentation["labels"].update(result_success="抵达工作台", result_failure="灯芯耗尽")
    revisions = {}
    append_stops(station, revisions, stops, configure_stop=configure_stop)
    publish_candidate(station, revisions)


if __name__ == "__main__":
    build()
