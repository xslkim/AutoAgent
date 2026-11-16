"""Build the green car contrast comparison as a separate playable package."""
from build_cinema import LIGHT_MS
from build_green_car import GreenCar
from build_train_stop import ART
from compiler import ROOT


class GreenCarContrast(GreenCar):
    generated = ROOT / "gunforge/level_design/generated/green_car_contrast"

    def __init__(self):
        super().__init__()
        self.source["id"] = "paper.green_car_contrast"

    def stage_art(self, stage, art=ART, ink_variant=None, light_ms=LIGHT_MS):
        return super().stage_art(stage, ART / "variants/green_car_contrast", ink_variant=ink_variant, light_ms=light_ms)


if __name__ == "__main__":
    GreenCarContrast().build()
