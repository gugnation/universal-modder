"""Turn a one-line gear idea into the full mod brief, ready to fill in and work from.

    um brief "Laser Rifle based on Brimstone from The Binding of Isaac"
    um brief "Shield based on the Aegis from Smite" --game "Borderlands 2"
    um brief --gear "Grenade Mod" --thing "Holy Hand Grenade" --source "Monty Python" --out BRIEF.md
    um brief "..." --json                     # fields only, for scripts

The phrase is "<Gear Type> based on <Weapon or Object/Thing> from <Source Material>". The output is the
brief template with every slot filled. The `<...>` slots left in it (how it acts, the behaviours it needs,
the parody name) are the agent's to research and fill: see skills/gear-brief/SKILL.md, which also says
which extra bullets to add for the item.
Default game: Borderlands: The Pre-Sequel.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from um.common import die

DEFAULT_GAME = "Borderlands: The Pre-Sequel"

PHRASE = re.compile(r"^\s*(?:an?\s+)?(?P<gear>.+?)\s+based\s+on\s+(?P<thing>.+?)\s+from\s+(?P<source>.+?)\s*[.!]?\s*$", re.I)
# "Brimstone from The Binding of Isaac" also comes as "The Binding of Isaac's Brimstone"
POSSESSIVE = re.compile(r"^\s*(?:an?\s+)?(?P<gear>.+?)\s+based\s+on\s+(?P<source>.+?)['’]s?\s+(?P<thing>.+?)\s*[.!]?\s*$", re.I)


def parse(phrase: str) -> dict:
    m = PHRASE.match(phrase) or POSSESSIVE.match(phrase)
    if not m:
        die('expected "<Gear Type> based on <Weapon or Object/Thing> from <Source Material>" '
            '(or "... based on <Source>\'s <Thing>"), or pass --gear/--thing/--source')
    return {k: m.group(k).strip().strip("\"'") for k in ("gear", "thing", "source")}


def render(gear: str, thing: str, source: str, game: str = DEFAULT_GAME) -> str:
    bullets = [
        f"Make a {gear} based on {thing} from {source}.",
        f"Make sure that the {gear}'s name is not called \"{source}\". Make it a parody or a reference to the source "
        f"material that fits it (like they do in the Borderlands games). Name: <parody name>. Red text: <one-line "
        f"in-joke referencing {source}>.",
        f"Make the {gear} function exactly like {thing} from {source} (<how it acts>, <behaviors it needs>, damage "
        f"application, etc.) while ensuring it feels and plays naturally within {game}'s gunplay, gear, stats, and systems.",
        f"Ensure the {gear} properly integrates with all existing mod systems (rarity, drop tables, inventory, UI, VFX, "
        f"audio, etc.). Verify correct drop behavior, rarity display, and teleporter-boss-only acquisition.",
        f"Confirm the {gear}'s model, animations, effects, and audio match the high-quality Borderlands aesthetic while "
        f"clearly referencing {source}.",
        f"Test the {gear} thoroughly in single-player to ensure full functionality and balance.",
        f"Use all of the assets, audio, code, models and animations at the highest quality and resolution, and make it "
        f"exactly like how it is in {game} (very important). Do not downscale anything.",
    ]
    return f"# {gear} based on {thing} from {source}\n\n" + "\n\n".join(f"* {b}" for b in bullets) + "\n"


def main(a):
    if a.phrase:
        f = parse(a.phrase)
    else:
        if not (a.gear and a.thing and a.source):
            die("give a phrase, or all of --gear, --thing and --source")
        f = dict(gear=a.gear, thing=a.thing, source=a.source)
    for k in ("gear", "thing", "source"):
        if getattr(a, k):
            f[k] = getattr(a, k)
    f["game"] = a.game
    text = json.dumps(f, indent=1) if a.json else render(**f)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"wrote {a.out}")
    else:
        print(text)


def register(sub):
    import argparse
    p = sub.add_parser("brief", help="expand '<Gear> based on <Thing> from <Source>' into the full gear brief",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("phrase", nargs="?", help='e.g. "Laser Rifle based on Brimstone from The Binding of Isaac"')
    p.add_argument("--gear", help="gear type (overrides the phrase)")
    p.add_argument("--thing", help="weapon or object/thing (overrides the phrase)")
    p.add_argument("--source", help="source material (overrides the phrase)")
    p.add_argument("--game", default=DEFAULT_GAME, help=f"game the gear goes into (default: {DEFAULT_GAME})")
    p.add_argument("--out", help="write the brief to this file instead of printing it")
    p.add_argument("--json", action="store_true", help="print the parsed fields as JSON")
    p.set_defaults(func=main)
