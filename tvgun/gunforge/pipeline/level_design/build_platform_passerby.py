"""Stage the T10 passerby as a protected passenger in the train-platform encounter."""
from build_cinema import permission, topic
from build_platform_contrast import PlatformContrast
from build_train_station_hardened import attach_eyes
from build_train_stop import GAME
from compiler import ROOT


class PlatformPasserby(PlatformContrast):
    generated = ROOT / "gunforge/level_design/generated/platform_passerby"
    resident_name = "路人"

    def __init__(self):
        super().__init__()
        self.source["id"] = "paper.platform_passerby"

    def platform_resident(self, data):
        folder = GAME / "reports/art/T10/assets/passerby_a_sheet"
        slot = {"id": "passerby_a", "rect": data["rect"]}
        resident, rescue = self.resident(self.stage, slot, folder=folder, ink_size=(228, 208))
        self.event(f"{rescue}.freed", topic("target.neutralized", rescue), [permission(resident, "decoration")])
        return resident, rescue

    def author(self):
        source = super().author()
        attach_eyes(self)
        return source


if __name__ == "__main__":
    PlatformPasserby().build()
