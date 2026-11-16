"""Build the platform contrast comparison as a separate playable package."""
from build_cinema import LIGHT_MS
from build_platform import Platform
from build_train_stop import ART
from compiler import ROOT


class PlatformContrast(Platform):
    generated = ROOT / "gunforge/level_design/generated/platform_contrast"

    def __init__(self):
        super().__init__()
        self.source["id"] = "paper.platform_contrast"

    def stage_art(self, stage, art=ART, ink_variant=None, light_ms=LIGHT_MS):
        return super().stage_art(stage, ART / "variants/platform_contrast", ink_variant=ink_variant, light_ms=light_ms)


if __name__ == "__main__":
    PlatformContrast().build()
