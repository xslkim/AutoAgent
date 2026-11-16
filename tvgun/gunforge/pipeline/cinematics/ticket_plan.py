from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "games/g01/cinematics/last_ticket"
SHOTS = [
    ("rain", 8, "Low camera tracks gently along the wet platform toward the closed dark station door. Fine rain and moving ripples. Distant jade train stands still; fixed dim night light."),
    ("keeper", 9, "The adult station attendant looks from her damp ticket toward the dark entrance, quietly worried. One small head movement, fingers tighten slightly, rain beyond the canopy. Keep face, clothing, ticket, station fixed."),
    ("ticket", 8, "Macro. Tiny droplets of rain creep along the pulp fibers of the ticket. Black ink slowly eats only one blank corner, with little feathered ink tendrils. Fingers stay still. No writing."),
    ("market", 9, "Slow level lateral camera glide along the shuttered night market. The narrow amber light beam moves across a window, it glows gently, then a second window follows. Reflections ripple in rain. Keep architecture fixed and sky dark."),
    ("path", 9, "Warm narrow light gently advances along the pavement from camera-right. Black liquid ink retreats from the light with little strands and vapor, uncovering the dry paper path up the steps. No flash and no new objects."),
    ("cinema", 8, "The projector's spools begin turning steadily. Amber light softly powers up in the same narrow beam. Small dust drifts in it. A gentle forward camera move. Dark empty seats stay fixed."),
    ("windows", 8, "Slow tracking move alongside the olive green stationary train. Three adjacent windows come gently alive in sequence with small muted amber lights, with a few raindrops sliding on glass. Train does not move yet."),
    ("boarding", 10, "One woman in muted jade wearing the same canvas satchel walks forward and takes two steps into the open carriage door. Film from behind and slowly follow. Her proportions, outfit and train remain consistent, calm ordinary motion. No new figures."),
    ("depart", 10, "The green train rolls away slowly along its existing track toward frame right, warm windows moving one by one, with restrained rain and mist. Fixed calm night exposure, camera stays on platform, no sudden brightness."),
    ("home", 11, "Quiet tracking shot looking through moving train window. The woman sits nearly motionless then gives a tiny relieved smile; reflections of little distant houses move horizontally across glass. The blank ticket remains on the sill. No letters."),
]
LINES = [
    (1.5, "我们那儿啊，末班车每天夜里只等一声铃。"),
    (10.5, "那晚，站上有人攥着张车票，连站台在哪儿都找不着了。"),
    (19.0, "墨把路吃了。票还在，回家的路没了。"),
    (28.2, "后来，夜市那头亮了一扇窗。"),
    (37.0, "只照亮脚下那么一点儿，也够往前走一步。"),
    (47.0, "接着是影院的灯。再往前，就看见车窗了。"),
    (64.5, "车门合上前，她终于赶到了。"),
    (81.0, "那张票早就湿透了。可她记得，灯是怎么一盏盏亮起来的。"),
]
VOICE_STYLE = "七十五岁北方老爷爷，温和低沉、略沙哑，口语自然，有气息感，像在雨夜给孙辈说一桩旧事。慢一点，句末放轻。普通话。"
