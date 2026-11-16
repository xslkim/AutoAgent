"""Build the waiting-room contrast comparison as a separate playable package."""
from build_cinema import LIGHT_MS
from build_train_stop import ART
from build_waiting_room import WaitingRoom
from compiler import ROOT


class WaitingRoomContrast(WaitingRoom):
    generated = ROOT / "gunforge/level_design/generated/waiting_room_contrast"

    def __init__(self):
        super().__init__()
        self.source["id"] = "paper.waiting_room_contrast"

    def stage_art(self, stage, art=ART, ink_variant=None, light_ms=LIGHT_MS):
        return super().stage_art(stage, ART / "variants/waiting_room_contrast", ink_variant=ink_variant, light_ms=light_ms)


if __name__ == "__main__":
    WaitingRoomContrast().build()
