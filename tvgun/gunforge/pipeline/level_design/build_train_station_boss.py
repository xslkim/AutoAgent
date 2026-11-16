"""Play the four train-station battles followed by the workbench boss."""
from build_train_station_hardened import main
from build_train_station_readability import CONTRAST_STOPS
from build_workbench_boss import WorkbenchBoss


BOSS_STOPS = (*CONTRAST_STOPS, WorkbenchBoss)


if __name__ == "__main__":
    main(package="paper.train_station_boss", stops=BOSS_STOPS)
