// Gear Prompt Forge: a small Windows app that fills in the Borderlands: The
// Pre-Sequel gear prompt template (same template as skills/bltps-gear-prompt).
// Auto-fill asks Claude through an Anthropic API key, or through Claude Code
// (`claude -p`) when it is installed. Everything else works offline. Build with build.sh.
package main

import (
	"strings"

	"github.com/lxn/walk"
	. "github.com/lxn/walk/declarative"
)

const closer = "TAKE ALL OF THE ASSETS, AUDIO, ALL THE CODE, EVERY MODEL AND ALL ANIMATIONS FOR EVERYTHING, USE THE HIGHEST QUALITY & RESOLUTION AND MAKE IT EXACTLY LIKE HOW IT IS IN BORDERLANDS THE PRE-SEQUEL, OTHER GAMES WHEN NEEDED AND MOST IMPORTANTLY THE SOURCE MATERIAL OR GET SAFE FILES OFF OF THE INTERNET (VERY IMPORTANT). DO NOT DOWNSCALE ANYTHING."

func or(s, placeholder string) string {
	if s = strings.TrimSpace(s); s == "" {
		return placeholder
	}
	return strings.TrimSuffix(s, ".")
}

func buildPrompt(g, t, s, how, beh, extras string) string {
	g, t, s = or(g, "[Gear Type]"), or(t, "[Weapon or Object/Thing]"), or(s, "[Source Material]")
	lines := []string{
		"* Make a " + g + " based on " + t + " from " + s + ".",
		"* Make sure that the " + g + "'s name is not called \"" + t + " or " + s + ", Make it a parody or a reference to the source material that fits it (like they do in the borderlands games)].",
		"* Make the " + g + " function exactly like " + t + " from " + s + " (" + or(how, "[how it acts]") + ", " + or(beh, "[behaviors it needs]") + ", damage application, etc.) while ensuring it feels and plays naturally within Borderlands: The Pre-Sequel’s gunplay, gear, stats, and systems.",
		"* Ensure the " + g + " properly integrates with all existing mod systems (rarity, drop tables, inventory, UI, VFX, audio, etc.). Verify correct drop behavior, rarity display, and teleporter-boss-only acquisition.",
		"* Confirm the " + g + "'s model, animations, effects, and audio match the high-quality Borderlands aesthetic while clearly referencing " + s + ".",
		"* Test the weapon thoroughly in both single-player & multiplayer/online co-op to ensure full functionality and balance.",
	}
	for _, e := range strings.Split(strings.ReplaceAll(extras, "\r", ""), "\n") {
		e = strings.TrimSpace(strings.TrimPrefix(strings.TrimSpace(e), "*"))
		if e != "" {
			lines = append(lines, "* "+e)
		}
	}
	lines = append(lines, closer)
	return strings.Join(lines, "\r\n\r\n")
}

func main() {
	var mw *walk.MainWindow
	var gear, thing, source *walk.LineEdit
	var how, beh, extras, out *walk.TextEdit
	var status *walk.Label
	var keyEdit *walk.LineEdit
	var autoBtn *walk.PushButton

	update := func() {
		if out == nil || gear == nil || thing == nil || source == nil || how == nil || beh == nil || extras == nil {
			return
		}
		out.SetText(buildPrompt(gear.Text(), thing.Text(), source.Text(), how.Text(), beh.Text(), extras.Text()))
		if status != nil {
			status.SetText("")
		}
	}

	big := Font{Family: "Segoe UI", PointSize: 11}
	fixed := Font{Family: "Segoe UI", PointSize: 12, Bold: true}

	err := MainWindow{
		AssignTo: &mw,
		Title:    "Gear Prompt Forge",
		MinSize:  Size{Width: 760, Height: 640},
		Size:     Size{Width: 980, Height: 820},
		Font:     Font{Family: "Segoe UI", PointSize: 10},
		Layout:   VBox{Margins: Margins{Left: 14, Top: 12, Right: 14, Bottom: 12}, Spacing: 8},
		Children: []Widget{
			Composite{
				Layout: Grid{Columns: 5, MarginsZero: true, Spacing: 8},
				Children: []Widget{
					Label{Text: "Gear Type"},
					Label{Text: ""},
					Label{Text: "Weapon or Object/Thing"},
					Label{Text: ""},
					Label{Text: "Source Material"},
					LineEdit{AssignTo: &gear, Font: big, CueBanner: "Laser Rifle", OnTextChanged: update},
					Label{Text: "based on", Font: fixed},
					LineEdit{AssignTo: &thing, Font: big, CueBanner: "Brimstone", OnTextChanged: update},
					Label{Text: "from", Font: fixed},
					LineEdit{AssignTo: &source, Font: big, CueBanner: "The Binding of Isaac", OnTextChanged: update},
				},
			},
			Composite{
				Layout: HBox{MarginsZero: true, Spacing: 8},
				Children: []Widget{
					PushButton{
						AssignTo: &autoBtn,
						Text:     "Auto-fill with Claude",
						OnClicked: func() {
							g, t, s := strings.TrimSpace(gear.Text()), strings.TrimSpace(thing.Text()), strings.TrimSpace(source.Text())
							key := strings.TrimSpace(keyEdit.Text())
							if g == "" || t == "" || s == "" {
								status.SetText("Fill in all three boxes first.")
								return
							}
							if key == "" && !hasClaudeCLI() {
								status.SetText("Paste an Anthropic API key, or install Claude Code to use your Claude account.")
								keyEdit.SetFocus()
								return
							}
							if key != "" {
								saveKey(key)
							}
							autoBtn.SetEnabled(false)
							status.SetText("Claude is thinking... (usually 10-40 seconds)")
							go func() {
								res, err := fillIn(key, g, t, s)
								mw.Synchronize(func() {
									autoBtn.SetEnabled(true)
									if err != nil {
										status.SetText("Auto-fill failed: " + err.Error())
										return
									}
									how.SetText(res.HowItActs)
									beh.SetText(res.Behaviors)
									extras.SetText(strings.Join(res.Extras, "\r\n"))
									update()
									status.SetText("Filled in. Edit anything you like, then copy.")
								})
							}()
						},
					},
					Label{Text: "Anthropic API key (optional if Claude Code is installed):"},
					LineEdit{AssignTo: &keyEdit, PasswordMode: true, CueBanner: "sk-ant-...", Text: loadKey()},
				},
			},
			Label{Text: "How it acts (optional, fills [how it acts])"},
			TextEdit{AssignTo: &how, MinSize: Size{Height: 44}, VScroll: true, OnTextChanged: update},
			Label{Text: "Behaviors it needs (optional, fills [behaviors it needs])"},
			TextEdit{AssignTo: &beh, MinSize: Size{Height: 44}, VScroll: true, OnTextChanged: update},
			Label{Text: "Extra * bullets (optional, one per line)"},
			TextEdit{AssignTo: &extras, MinSize: Size{Height: 60}, VScroll: true, OnTextChanged: update},
			Label{Text: "Your prompt"},
			TextEdit{AssignTo: &out, ReadOnly: true, VScroll: true, StretchFactor: 4, Font: Font{Family: "Segoe UI", PointSize: 10}},
			Composite{
				Layout: HBox{MarginsZero: true},
				Children: []Widget{
					PushButton{
						Text: "Copy for Word",
						OnClicked: func() {
							if err := walk.Clipboard().SetText(out.Text()); err != nil {
								status.SetText("Couldn't copy. Select the text and press Ctrl+C.")
								return
							}
							status.SetText("Copied. Paste it into Word.")
						},
					},
					PushButton{
						Text: "Clear",
						OnClicked: func() {
							for _, e := range []*walk.LineEdit{gear, thing, source} {
								e.SetText("")
							}
							for _, e := range []*walk.TextEdit{how, beh, extras} {
								e.SetText("")
							}
							update()
							gear.SetFocus()
						},
					},
					Label{AssignTo: &status},
					HSpacer{},
				},
			},
		},
	}.Create()
	if err != nil {
		walk.MsgBox(nil, "Gear Prompt Forge", err.Error(), walk.MsgBoxIconError)
		return
	}
	update()
	mw.Run()
}
