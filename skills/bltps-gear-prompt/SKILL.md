---
name: bltps-gear-prompt
description: Turn a one-line gear idea into the user's saved Borderlands The Pre-Sequel gear-creation prompt template. Use whenever the user writes "[Gear Type] based on [Weapon or Object/Thing] from [Source Material]" (e.g. "Laser Rifle based on The Binding of Isaac's Brimstone", "Oz Kit based on Mario's Cape Feather", "Shield based on Halo's Bubble Shield"). Output the filled-in template only, as copy-paste text for a Word document; do not start building the mod.
---

# Borderlands: The Pre-Sequel gear prompt

When the user says **`[Gear Type] based on [Weapon or Object/Thing] from [Source Material]`**, reply with the
template below, filled in. The user pastes it into a Word document to use later, so:

- **Don't start modding.** No recon, no code, no file changes. Just write the template.
- Put the result in a single fenced ```text block so it copies cleanly, with nothing else inside the block.
- Keep every line of the template **word for word** (typos and phrasing included). Only replace the
  bracketed placeholders. Keep the `*` bullets and the closing all-caps paragraph.
- Fill `[how it acts]` and `[behaviors it needs]` with concrete, specific mechanics of the real item
  (fire pattern, charge time, beam/projectile behaviour, piercing, status effects, synergies, sounds, visual
  tells). Research the item if you aren't sure; don't guess vaguely.
- `[Gear]` and `[Gear Type]` are both the gear type (e.g. "Laser Rifle").
- After the original bullets, you **may add extra `*` bullets** that would help build the item, specific to
  it. Good candidates: a suggested parody name or two plus red-text flavour line, manufacturer (Hyperion,
  Jakobs, Maliwan, Tediore, Torgue, Vladof, Dahl, Bandit/Scav, Atlas, Eridian lasers...), rarity/legendary
  status, element (incl. Cryo), how it works with low gravity, Oz kits and
  oxygen, butt slams, character-specific interactions (Athena, Wilhelm, Nisha, Claptrap, Jack, Aurelia),
  scaling across levels/UVHM, and card stats. Only add bullets that help this item. Never add a "Dropped by" bullet or name a
  boss or enemy that drops it: drops are random, with no dedicated drop source.
- Outside the code block, add at most one short line (e.g. what you added). No other commentary.

## Template

```text
* Make a [Gear Type] based on [Weapon or Object/Thing] from [Source Material].

* Make sure that the [Gear]'s name is not called "[Weapon or Object/Thing] or [Source Material], Make it a parody or a reference to the source material that fits it (like they do in the borderlands games)].

* Make the [Gear Type] function exactly like [Weapon or Object/Thing] from [Source Material] ([how it acts], [behaviors it needs], damage application, etc.) while ensuring it feels and plays naturally within Borderlands: The Pre-Sequel’s gunplay, gear, stats, and systems.

* Ensure the [Gear Type] properly integrates with all existing mod systems (rarity, drop tables, inventory, UI, VFX, audio, etc.). Verify correct drop behavior, rarity display, and teleporter-boss-only acquisition.

* Confirm the [Gear Type]'s model, animations, effects, and audio match the high-quality Borderlands aesthetic while clearly referencing [Source Material].

* Test the weapon thoroughly in both single-player & multiplayer/online co-op to ensure full functionality and balance.

[optional extra * bullets go here]

TAKE ALL OF THE ASSETS, AUDIO, ALL THE CODE, EVERY MODEL AND ALL ANIMATIONS FOR EVERYTHING, USE THE HIGHEST QUALITY & RESOLUTION AND MAKE IT EXACTLY LIKE HOW IT IS IN BORDERLANDS THE PRE-SEQUEL, OTHER GAMES WHEN NEEDED AND MOST IMPORTANTLY THE SOURCE MATERIAL OR GET SAFE FILES OFF OF THE INTERNET (VERY IMPORTANT). DO NOT DOWNSCALE ANYTHING.
```

## Example

User: `Laser Rifle based on The Binding of Isaac’s Brimstone`

```text
* Make a Laser Rifle based on Brimstone from The Binding of Isaac.

* Make sure that the Laser Rifle's name is not called "Brimstone or The Binding of Isaac, Make it a parody or a reference to the source material that fits it (like they do in the borderlands games)].

* Make the Laser Rifle function exactly like Brimstone from The Binding of Isaac (hold fire to charge, release to fire a thick blood-red beam that travels the full length of the room and passes through every enemy in its path, a short sustained beam rather than single shots, a visible charge-up that must be full before release, no firing while charging, the beam locks to the aim direction when released, rapid damage ticks on everything it touches for the whole beam duration, damage application, etc.) while ensuring it feels and plays naturally within Borderlands: The Pre-Sequel’s gunplay, gear, stats, and systems.

* Ensure the Laser Rifle properly integrates with all existing mod systems (rarity, drop tables, inventory, UI, VFX, audio, etc.). Verify correct drop behavior, rarity display, and teleporter-boss-only acquisition.

* Confirm the Laser Rifle's model, animations, effects, and audio match the high-quality Borderlands aesthetic while clearly referencing The Binding of Isaac.

* Test the weapon thoroughly in both single-player & multiplayer/online co-op to ensure full functionality and balance.

* Name ideas: "Hellfire Tantrum" or "Mom's Disappointment", red text: "Mama's going to be so upset."

* Make it a Legendary Maliwan-style laser with the Fire element and a blood-red beam, with damage ticks that scale to player level and UVHM.

* The charge stays full while airborne or butt-slamming, and holding fire while in low gravity keeps the beam aimed as the player drifts.

TAKE ALL OF THE ASSETS, AUDIO, ALL THE CODE, EVERY MODEL AND ALL ANIMATIONS FOR EVERYTHING, USE THE HIGHEST QUALITY & RESOLUTION AND MAKE IT EXACTLY LIKE HOW IT IS IN BORDERLANDS THE PRE-SEQUEL, OTHER GAMES WHEN NEEDED AND MOST IMPORTANTLY THE SOURCE MATERIAL OR GET SAFE FILES OFF OF THE INTERNET (VERY IMPORTANT). DO NOT DOWNSCALE ANYTHING.
```
