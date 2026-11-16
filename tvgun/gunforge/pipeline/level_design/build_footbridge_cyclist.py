"""Place the paper cyclist and his parked bicycle on the upper footbridge."""
from PIL import Image

from build_cinema import after
from build_footbridge import Footbridge, STAGE
from build_video_shop import ART
from compiler import ROOT


SHEET = ART / "assets/cyclist_sheet"
BICYCLE = ART / "assets/bicycle/texture.png"
DECK_Y = 456


class FootbridgeCyclist(Footbridge):
    generated = ROOT / "gunforge/level_design/generated/footbridge_cyclist"

    def __init__(self):
        super().__init__()
        self.source["id"] = "paper.footbridge_cyclist"

    def scenery(self):
        resident, reaction, bicycle = "bridge.cyclist_resident", "bridge.cyclist_reaction", "bridge.bicycle"
        names = (resident, reaction)
        depth = self.presentation["layers"][f"{STAGE}.bridge"]["parallax"]
        poses = []
        for name in ("idle", "startle"):
            with Image.open(SHEET / f"pose_{name}.png") as image:
                poses.append(image.convert("RGBA"))
        bounds = [image.getchannel("A").getbbox() for image in poses]
        # Keep the paper feet at the same anchor when the resident reacts to the bell.
        crop = (min(box[0] for box in bounds), min(box[1] for box in bounds),
                max(box[2] for box in bounds), max(box[3] for box in bounds))
        scale = 240 / (bounds[0][3] - bounds[0][1])
        width = round((crop[2] - crop[0]) * scale)
        height = round((crop[3] - crop[1]) * scale)
        rect = (400, DECK_Y - height, width, height)
        for identifier, pose, visible in zip(names, poses, (True, False)):
            path = self.write_image(identifier.removeprefix("bridge."), pose.crop(crop))
            self.entity(identifier, "decoration", rect, path, z=55, parallax=depth, visible=visible)
        with Image.open(BICYCLE) as image:
            width, height = 244, round(image.height * 244 / image.width)
        self.entity(bicycle, "decoration", (460, DECK_Y - height, width, height), BICYCLE, z=54, parallax=depth)

        def visibility(startled):
            return [{"op": "set", "entity": identifier, "field": "visible", "value": value}
                    for identifier, value in zip(names, (not startled, startled))]

        for number in range(1, 4):
            alert = f"bridge.cyclist_resident.react{number}"
            self.event(alert, after(f"bridge.cart{number}.warn", 0), visibility(True))
            self.event(f"{alert}.end", after(alert, 700), visibility(False))
        return resident, reaction, bicycle

    def author(self):
        source = super().author()
        self.sections[STAGE]["hint"] = "射亮右上灯笼，等滴墨入光。听到车铃时，打断桥下的墨车夫。"
        return source


if __name__ == "__main__":
    FootbridgeCyclist().build()
