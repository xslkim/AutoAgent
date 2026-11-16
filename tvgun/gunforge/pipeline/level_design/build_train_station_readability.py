"""Combine the contrast and hardened-eye samples for the T13 art review."""
from build_green_car_contrast import GreenCarContrast
from build_lantern_pullback import LanternPullback
from build_platform_contrast import PlatformContrast
from build_train_station_hardened import main
from build_waiting_room_contrast import WaitingRoomContrast


CONTRAST_STOPS = (WaitingRoomContrast, PlatformContrast, GreenCarContrast)


if __name__ == "__main__":
    main(package="paper.train_station_readability",
         stops=(*CONTRAST_STOPS, LanternPullback))
