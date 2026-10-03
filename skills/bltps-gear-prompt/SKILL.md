---
name: bltps-gear-prompt
description: Write out the user's saved Borderlands: The Pre-Sequel gear-request template, filled in. Use whenever the user says "<Gear Type> based on <Weapon or Object/Thing> from <Source Material>" (e.g. "Laser Rifle based on The Binding of Isaac's Brimstone"), or asks for their BL:TPS gear prompt/template. Output is text for their Word document, not mod work.
---

# BL:TPS gear prompt

The user keeps these prompts in a Word document to use later. When they write
**`[Gear Type] based on [Weapon or Object/Thing] from [Source Material]`**, reply with the template below
filled in. Do not start modding, scanning or generating assets: the deliverable is the text.

## Rules
- Output the filled template inside one ```` ```text ```` block so the `*` bullets survive copy-paste into
  Word. At most one short line before it; nothing after it.
- Keep the user's wording **exactly**: same bullets, same order, same spelling and punctuation, and the
  closing all-caps paragraph verbatim. Only replace the bracketed placeholders:
  - `[Gear Type]` and `[Gear]` → the gear type as the user wrote it (e.g. `Laser Rifle`).
  - `[Weapon or Object/Thing]` → the weapon or thing (e.g. `Brimstone`).
  - `[Source Material]` → the source (e.g. `The Binding of Isaac`). In the naming bullet this is the
    name the gear must *not* use, so substitute it there too.
  - `[how it acts], [behaviors it needs]` → concrete, accurate specifics of how the original works
    (fire pattern, charge/cooldown, projectile or beam behaviour, status effects, synergies, sounds, tells).
    Be specific to the source; if unsure of a detail, say what to verify rather than inventing it.
- Add extra `*` bullets where they help build the item (marked **EXTRA** below). Insert them after the
  "function exactly like" bullet and before the integration bullet, so the user's bullets keep their
  relative order. Make them specific to this item, not generic filler. Good extras:
  - A suggested parody name or two and red-text flavour line, in Borderlands humour.
  - Manufacturer and rarity that fit (BL:TPS manufacturers: Bandit/Scav, Dahl, Hyperion, Jakobs, Maliwan,
    Tediore, Torgue, Vladof; lasers only from Dahl, Hyperion, Maliwan, Tediore, Vladof, Scav), and how
    the manufacturer's quirk interacts with the mechanic (e.g. Tediore reload-throw, Vladof spin-up).
  - Element (incl. BL:TPS cryo and laser-specific behaviour) and how it maps to the source's effects.
  - How it uses BL:TPS-only systems: low gravity, Oz kits/oxygen, butt-slam, ice/cryo freeze, Grinder.
  - Stat card targets (damage, fire rate, accuracy, magazine/charge, reload), level scaling, and what
    keeps it balanced against existing legendaries/uniques.
  - Model/VFX/audio reference points from the source (iconic shape, colours, sounds) and how to blend
    them with the Borderlands cel-shaded, hand-painted look.
- If any part of the request is missing (no source, ambiguous item), ask once instead of guessing.

## Template

```text
* Make a [Gear Type] based on [Weapon or Object/Thing] from [Source Material]. 

* Make sure that the [Gear]'s name is not called "[Source Material]", Make it a parody or a reference to the source material that fits it (like they do in the borderlands games)].

* Make the [Gear Type] function exactly like [Weapon or Object/Thing] from [Source Material] ([how it acts], [behaviors it needs], damage application, etc.) while ensuring it feels and plays naturally within Borderlands: The Pre-Sequel’s gunplay, gear, stats, and systems.

* EXTRA bullets go here.

* Ensure the [Gear Type] properly integrates with all existing mod systems (rarity, drop tables, inventory, UI, VFX, audio, etc.). Verify correct drop behavior, rarity display, and teleporter-boss-only acquisition.

* Confirm the [Gear Type]'s model, animations, effects, and audio match the high-quality Borderlands aesthetic while clearly referencing [Source Material].

* Test the weapon thoroughly in both single-player to ensure full functionality and balance.


TAKE ALL OF THE ASSETS, AUDIO, ALL THE CODE, EVERY MODEL AND ALL ANIMATIONS FOR EVERYTHING, USE THE HIGHEST QUALITY & RESOLUTION AND MAKE IT EXACTLY LIKE HOW IT IS IN BORDERLANDS THE PRE-SEQUEL (VERY IMPORTANT). DO NOT DOWNSCALE ANYTHING.
```

Replace the `* EXTRA bullets go here.` line with the extra bullets (or drop it if none help).
