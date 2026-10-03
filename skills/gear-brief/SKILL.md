---
name: gear-brief
description: Expand a one-line gear idea of the form "<Gear Type> based on <Weapon or Object/Thing> from <Source Material>" (e.g. "Laser Rifle based on The Binding of Isaac's Brimstone") into the user's full Borderlands-style gear brief, with the source item's real behaviour, a parody name and extra item-specific bullets filled in. Use whenever the user writes a line in that shape, or asks for a gear/weapon/shield/grenade/class-mod/relic/O2-kit brief for Borderlands: The Pre-Sequel (or another Borderlands game).
---

# Gear brief

The user writes ideas as one line: **`<Gear Type> based on <Weapon or Object/Thing> from <Source Material>`**.
They want back their brief template, fully written out, not a summary. It then becomes the spec the
**mod-any-game** loop builds from. Default game: **Borderlands: The Pre-Sequel** (use another only if they
name it).

## Steps
1. Run `um brief "<their line>"` (add `--game "<game>"` if they named a different one). It parses both the
   "X from Source" and the "Source's X" forms and prints the template with Gear, Thing, Source and Game
   filled in. `--out BRIEF.md` writes it to a file.
2. Fill every `<...>` slot yourself. Never hand back a placeholder:
   - **Parody name.** Not the source's name. Borderlands-style: a pun, an in-joke or a misquote that
     someone who knows the source gets at once (Hyperion "Conference Call", Torgue "Unkempt Harold"). Add a
     short red-text line too: the weapon's special-effect flavour text, also a reference.
   - **How it acts / behaviors it needs.** Describe the source item precisely: charge or wind-up, fire
     pattern, projectile vs hitscan vs beam, pierce, bounce, homing, duration, tick rate, how damage scales
     with the wielder's stats, synergies, and what it replaces or blocks (e.g. Brimstone stops normal
     tears). If you aren't sure of a mechanic, look it up on the source's wiki; don't invent it.
3. **Add extra bullets** whenever they help build the item (the user asked for this). Good ones:
   - **Mapping to Borderlands systems:** manufacturer and why (Maliwan for elemental lasers, Jakobs for
     fire-as-fast-as-you-click, Torgue for explosive, Hyperion for accuracy-builds-up, Dahl for burst, Vladof
     for fire rate, Tediore for reload-throw, Scav for oddballs in TPS); weapon class; element; rarity
     (legendary / E-tech / glitch / pearlescent / unique); level scaling; which card stats the item uses.
   - **Damage application:** what the card damage means (per tick, per beam, per pellet), ammo per shot,
     crit and elemental behaviour, and how it interacts with TPS slams, cryo and the O2/oxygen system.
   - **Parts and visuals:** barrel, body, sight, accessory and material parts to reuse or reskin;
     particle systems; firing, charge and impact sounds; the reload animation.
   - **Drop source:** which teleporter boss(es), the drop rate, and how it shows in the loot beam and the
     card.
   - **Balance targets:** where it sits against existing legendaries at the same level.
   - **Edge cases:** Fragtrap / Claptrap action skills, Doppelganger copies, pickup, vendor selling, saving
     and reloading.
4. Reply with the finished brief as a markdown bullet list (`*` bullets, one blank line between them),
   matching the user's wording. Then offer, in one line, to start building it with the mod-any-game loop.

## Worked example
Input: `Laser Rifle based on The Binding of Isaac's Brimstone`

* Make a Laser Rifle based on Brimstone from The Binding of Isaac.

* Make sure that the Laser Rifle's name is not called "The Binding of Isaac". Make it a parody or a reference to the source material that fits it (like they do in the Borderlands games). Name: **Mom's Disappointment**. Red text: *"Deal with the Devil? Worth it."*

* Make the Laser Rifle function exactly like Brimstone from The Binding of Isaac (hold fire to charge; a charge meter fills over a time tied to the gun's fire rate; letting go early cancels the shot and fires nothing; at full charge, letting go fires a thick blood-red beam that reaches to the first wall, pierces every enemy in its path and hits each one several times over its short life; normal fire is replaced, so it can't fire while charging; damage application: every tick deals the card damage, so total damage per shot = card damage × ticks) while ensuring it feels and plays naturally within Borderlands: The Pre-Sequel's gunplay, gear, stats, and systems.

* Map it to TPS: Maliwan laser, legendary, Incendiary (blood/hellfire). Fire rate on the card scales the charge time; magazine size = full-charge shots per reload; one beam costs 3 laser cells. Crits apply per tick on weak points; elemental DoT rolls per tick at the card's chance.

* Ensure the Laser Rifle properly integrates with all existing mod systems (rarity, drop tables, inventory, UI, VFX, audio, etc.). Verify correct drop behavior, rarity display, and teleporter-boss-only acquisition.

* Confirm the Laser Rifle's model, animations, effects, and audio match the high-quality Borderlands aesthetic while clearly referencing The Binding of Isaac (a dark-red Maliwan body with a horned demon-face barrel shroud; a charge glow that pulses like Isaac's charge bar; the beam a thick, wavy blood-red ribbon with a dark core; a wet, gargling charge-up sound and a roaring release).

* Test the Laser Rifle thoroughly in single-player to ensure full functionality and balance (charge cancel, ticks against a single target vs a line of enemies, crit ticks, Doppelganger and Claptrap VaultHunter.EXE interactions, a save/reload with it equipped, and the drop from the teleporter boss only).

* Use all of the assets, audio, code, models and animations at the highest quality and resolution, and make it exactly like how it is in Borderlands: The Pre-Sequel (very important). Do not downscale anything.

## Building it in BL:TPS (when the user says go)
Hand off to **mod-any-game**. Notes for this game:
- **Engine:** Unreal Engine 3 (the same "Willow" codebase as Borderlands 2). Community routes, newest first:
  - Python SDK mods (bl-sdk's `unrealsdk` / willow2 mod manager), for custom behaviour like charge-and-beam;
  - BLCMM text mods (`set` commands plus offline hotfixes), for item definitions, parts, drop pools and
    stats.

  Check the current release and install steps before installing anything (ask before putting a loader in
  the game folder).
- **Read the game:** dump objects with the SDK or the `obj dump` console, and browse packages with UE Viewer
  (UModel) to find the parts, particles and sounds to reuse. Write the exact object paths into MODLOG.md.
- **Assets, "exactly like TPS, full resolution":** the most faithful result reuses and recombines the game's
  own meshes, materials, particle systems and sounds, referenced by object path from the user's install,
  at their native resolution. Brand-new meshes in cooked UE3 packages are hard, so prove the route with a
  vertical slice first. Generate only what the game lacks (fal), at the highest resolution the model
  offers, and never downscale. Extracted game assets stay on the user's machine, outside the repo and out
  of any release (`um publish check`).
- **Single-player only.** Mods that change gear can corrupt characters, so run `um backup create` on the
  save folder before every modded launch.
