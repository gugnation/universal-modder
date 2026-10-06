# The Binding of Isaac: Rebirth (Afterbirth+ / Repentance / Repentance+)

**Identify.** Steam app 250900, "The Binding of Isaac: Rebirth", in `steamapps/common/The Binding of Isaac Rebirth/`.
`isaac-ng.exe`, packed archives in `resources/packed/*.a`, and the Lua API's own definitions loose in
`resources/scripts/` (`enums.lua` lists every callback, flag and entity type). `resources-dlc3/` means
Repentance or later. `um scan isaac` reports the DLC, the mods present, whether resources were extracted and
whether REPENTOGON is installed.
- Native C++ engine, but with an official **Lua 5.3 mod API** (since Afterbirth+). Mods are folders of Lua,
  XML and PNG/ANM2. No DLL injection is needed for content.
- Target **Repentance+** (the current Steam build). Afterbirth+ tutorials are mostly obsolete: many APIs
  changed in Repentance. macOS stops at Afterbirth+.
- **No anti-cheat.** Repentance+ online co-op requires every mod to be disabled; mods are for single player
  and local co-op. Never use a mod to post daily-run or leaderboard results.
- Docs: the API reference at `wofsauge.github.io/IsaacDocs/rep/` (pick the `rep` pages), tutorials at
  `isaacblueprints.com`, REPENTOGON at `repentogon.com`.

## Folders
- **Mods:** `<install>/mods/<ModFolder>/`. Workshop mods are copied here as `<name>_<workshopid>`. Load
  order is alphabetical. A `disable.it` file in a mod folder disables it.
- **Saves, options, log:** `Documents/My Games/Binding of Isaac Repentance+/` (`Repentance` /
  `Afterbirth+` for older builds): `options.ini`, `log.txt`, `persistentgamedata<1-3>.dat`, `save_backups/`.
- **Steam Cloud** (the default, `SteamCloud=1` in options.ini): `<Steam>/userdata/<account>/250900/remote/`
  (`rep+persistentgamedata1.dat`). options.ini decides which copy the game reads, so back up **both** with
  `um backup create` before the first modded launch. `um scan` lists both.
- **Linux / Steam Deck (Proton):** the Documents folder is inside
  `steamapps/compatdata/250900/pfx/drive_c/users/steamuser/Documents/`.

## Lab setup
1. **Extract the vanilla files** with `<install>/tools/ResourceExtractor/ResourceExtractor.exe`. Repentance
   writes them into `resources/` and `resources-dlc3/`; Repentance+ writes a separate extracted-resources
   folder. These are the reference for every XML schema, sprite size and ANM2. Re-run after each game patch.
   They are game files: never copy them into the repo or ship them.
2. **Debug console:** set `EnableDebugConsole=1` in options.ini, open it with the `~` key in a run.
   - `giveitem c<id>` / `t<id>` (trinket) / `k<id>` (card) / `p<id>` (pill effect), or `giveitem <name>`,
     which also works for modded content. `g` is short for giveitem, `remove <name>` takes it away.
   - `spawn <type>.<variant>.<subtype>`, `stage 6`, `goto s.boss`, `restart`, `seed <SEED>`.
   - `debug 3` (invincible), `debug 8` (active always charged), `debug 10` (enemies melt), `debug 7` (damage
     numbers).
   - `luamod <ModFolder>` reloads a mod's Lua without restarting; `lua <code>` runs one line.
3. **Read `log.txt`** after every launch. Lua errors, XML errors and missing files land there; the console
   shows Lua errors in red. A crash right at startup is almost always malformed XML in `content/`.
4. `--luadebug` (Steam launch option) unlocks `io`, `os` and `debug` for **every** enabled mod. Use it only
   with your own mods enabled, never with Workshop mods.
5. **Windowed for automation:** `Fullscreen=0` in options.ini. Launch with `steam://rungameid/250900` and
   drive it with `um win`.

## Mod layout
```
mods/MyMod/
  metadata.xml       # name, directory, id (Workshop), version, visibility; the game creates it on first launch
  main.lua           # entry point
  scripts/mymod/     # more Lua, loaded with include("scripts.mymod.items")
  content/           # NEW things, merged with vanilla: items.xml, players.xml, pocketitems.xml,
                     # entities2.xml, costumes2.xml, itempools.xml, sounds.xml, music.xml
  resources/         # art, sounds and OVERRIDES at vanilla paths: gfx/items/collectibles/, gfx/characters/, ...
```
- `content/` **adds**; `resources/` **replaces** a vanilla file with the same path. A `content/items.xml`
  never needs vanilla entries in it.
- Modded IDs are assigned at load time. **Never hard-code them**: look them up by the XML `name`:
  `Isaac.GetItemIdByName`, `Isaac.GetTrinketIdByName`, `Isaac.GetCardIdByName`,
  `Isaac.GetPillEffectByName`, `Isaac.GetPlayerTypeByName(name, isTainted)`,
  `Isaac.GetEntityTypeByName` / `Isaac.GetEntityVariantByName`.
- Prefix every name and script path with the mod's name, since other mods share the same namespace.
- Use `include` rather than `require` for your own files: `require` caches, so `luamod` won't pick up edits.

## Content kinds
```lua
local mod = RegisterMod("MyMod", 1)
local JAR = Isaac.GetItemIdByName("Penny Jar")
mod:AddCallback(ModCallbacks.MC_EVALUATE_CACHE, function(_, player, flag)
  if flag == CacheFlag.CACHE_DAMAGE then
    player.Damage = player.Damage + 1.5 * player:GetCollectibleNum(JAR)
  end
end)
```
- **Passive item:** `<passive name="Penny Jar" description="Money is power" gfx="mymod_jar.png" quality="2"
  cache="damage"/>` in `content/items.xml`; the 32x32 PNG goes in `resources/gfx/items/collectibles/`.
  Stats change only in `MC_EVALUATE_CACHE`, for the flags listed in `cache`.
- **Active item:** `<active ... maxcharges="4"/>` + `MC_USE_ITEM` (filtered by the item id); return `true`
  to play the hold-up animation.
- **Item pools:** a new item never drops until it is in `content/itempools.xml` (treasure, shop, boss,
  devil, angel, secret, ...) with a weight.
- **Trinket:** `<trinket .../>` in items.xml, art in `gfx/items/trinkets/`; check
  `player:HasTrinket(id)` and scale effects with `player:GetTrinketMultiplier(id)` (golden / Mom's Box).
- **Card / rune:** `<card name= description= type="tarot" .../>` in `content/pocketitems.xml` +
  `MC_USE_CARD`. The HUD card front is the animation named by `hud=` in the mod's
  `content/gfx/ui_cardfronts.anm2`; the pickup on the floor is an `entities2.xml` card subtype (look the card
  up with `GetCardIdByName`, never spawn it by that subtype).
- **Pill effect:** `<pilleffect name= class=.../>` in pocketitems.xml (joins the pill pool automatically) +
  `MC_USE_PILL`.
- **Character:** `content/players.xml` (`name`, `skin`, hearts, `items`, `card`, `pill`, `costume`,
  `birthright`; `bSkinParent` makes the tainted version) + `MC_POST_PLAYER_INIT` checking
  `player:GetPlayerType()`. The skin repaints a vanilla character sheet in place; menu portraits, name images
  and costumes (`costumes2.xml`) are copied from the vanilla files and repainted.
- **Pickup / familiar / enemy / effect:** an `entities2.xml` entry (`id`, `variant`, `anm2path`, ...) plus
  callbacks: `MC_PRE_PICKUP_COLLISION`, `MC_FAMILIAR_INIT` / `MC_FAMILIAR_UPDATE` (spawn familiars from
  `MC_EVALUATE_CACHE` with `CacheFlag.CACHE_FAMILIARS` and `player:CheckFamiliar`), `MC_NPC_UPDATE`.
- **Mod save data:** `local json = require("json")`; `mod:SaveData(json.encode(t))` on `MC_PRE_GAME_EXIT`,
  `json.decode(mod:LoadData())` on `MC_POST_GAME_STARTED` (`mod:HasData()` first).

## Achievements and unlocks
- The vanilla API cannot add achievements or lock modded content behind them.
- **REPENTOGON** (a script extender for Repentance+, installed through its own launcher, kept outside the
  game folder or in `REPENTOGONLauncher/`) can:
  - `content/achievements.xml` adds real achievements (`name`, `text`, `gfx`, `hidden`), saved with the
    vanilla ones and shown with the vanilla popup;
  - `achievement="MyAch"` on entries in items.xml, players.xml and pocketitems.xml keeps them locked
    until it unlocks;
  - unlock with `Isaac.GetPersistentGameData():TryUnlock(Isaac.GetAchievementIdByName("MyAch"))`, and
    re-lock while testing with the `lockachievement` console command.
- For an expansion-sized mod with unlocks, build on REPENTOGON and say so on the mod page: players must
  install it. Check `REPENTOGON` before calling its functions, so a missing install fails with a message.
- Without REPENTOGON: keep your own unlock flags in `mod:SaveData`, remove locked items from the pools at run
  start (`Game():GetItemPool():RemoveCollectible(id)`), and show your own popup sprite.

## ANM2 sprites
Every animated thing (players, familiars, enemies, pickups, effects, HUD cards, menus) is an `.anm2`: XML
that cuts frames out of PNG spritesheets.
- `<Content>`: `Spritesheets` (`Path` is relative to the .anm2 file), `Layers` (each draws from one sheet),
  `Nulls` (attachment points with no image), `Events` (named triggers).
- `<Animations DefaultAnimation=...>`: each `Animation` (`Name`, `FrameNum`, `Loop`) has a `RootAnimation`
  (moves everything), `LayerAnimations` with `Frame`s (`XCrop`/`YCrop`/`Width`/`Height` in the sheet,
  `XPivot`/`YPivot`, position, scale, rotation, tint, `Delay` in game frames, `Interpolated`), and
  `Triggers` (`EventId`, `AtFrame`).
- The game animates at **30 fps**; `Delay="4"` holds a frame for 4 ticks.
- Generate one from a sheet: `um sprite anm2 out.anm2 sheet.png --frame 32x32 --anim Idle=0-3
  --anim Attack=4-7:once --event Shoot@Attack:2`. Inspect any vanilla file with `um sprite anm2-info`
  to learn the animation names it must keep (a replacement skin must provide every one of them).
- Editors: `tools/IsaacAnimationEditor/IsaacAnimationEditor.exe` (official) or anm2ed (open source).
- Lua: `local s = Sprite(); s:Load("gfx/mymod_thing.anm2", true); s:Play("Idle", true)`, then
  `s:Update()` / `s:Render(pos)`; swap art with `s:ReplaceSpritesheet(0, "gfx/alt.png"); s:LoadGraphics()`;
  react to events with `s:IsEventTriggered("Shoot")`. Entities use `entity:GetSprite()`.
- **Art rules:** PNGs must be 32-bit RGBA (save with `um sprite`, which writes RGBA; palette PNGs render wrong). Collectibles and
  trinkets are plain 32x32 PNGs, no ANM2. Isaac is chunky pixel art with a dark outline: draw at native
  size (`um sprite pixelate --size 32x32 --colors 24 --outline`), snap to vanilla colours with
  `um sprite palette --from <extracted vanilla sprite>`, and never smooth-scale.

## Ship
- Upload with `<install>/tools/ModUploader/ModUploader.exe`; it writes the Workshop `id` into
  metadata.xml. Ship only your own files: no extracted vanilla PNG/ANM2/XML, even edited copies of whole
  sheets you didn't redraw.
- Test the release folder with every other mod disabled, then with a few popular ones (EID, Mod Config Menu)
  enabled: name collisions and pool edits are the usual conflicts.
