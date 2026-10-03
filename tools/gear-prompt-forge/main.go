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
	displayFamily = loadFonts()

	var mw *walk.MainWindow
	var gear, thing, source *walk.LineEdit
	var how, beh, extras, out *walk.TextEdit
	var status *walk.Label
	var keyEdit *walk.LineEdit
	autoBtn := &lootButton{text: "AUTO-FILL WITH CLAUDE", col: colYellow}
	copyBtn := &lootButton{text: "COPY FOR WORD", col: colOrange}
	clearBtn := &lootButton{text: "CLEAR", col: colMuted}

	setStatus := func(t string, col walk.Color) {
		if status != nil {
			status.SetTextColor(col)
			status.SetText(t)
		}
	}
	update := func() {
		if out == nil || gear == nil || thing == nil || source == nil || how == nil || beh == nil || extras == nil {
			return
		}
		out.SetText(buildPrompt(gear.Text(), thing.Text(), source.Text(), how.Text(), beh.Text(), extras.Text()))
		setStatus("", colText)
	}

	autoBtn.onClick = func() {
		g, t, s := strings.TrimSpace(gear.Text()), strings.TrimSpace(thing.Text()), strings.TrimSpace(source.Text())
		key := strings.TrimSpace(keyEdit.Text())
		if g == "" || t == "" || s == "" {
			setStatus("Fill in all three boxes first.", colOrange)
			return
		}
		if key == "" && !hasClaudeCLI() {
			setStatus("Paste an Anthropic API key, or install Claude Code to use your Claude account.", colOrange)
			keyEdit.SetFocus()
			return
		}
		if key != "" {
			saveKey(key)
		}
		autoBtn.SetEnabled(false)
		autoBtn.SetText("CLAUDE IS THINKING...")
		setStatus("Usually 10-40 seconds.", colMuted)
		go func() {
			res, err := fillIn(key, g, t, s)
			mw.Synchronize(func() {
				autoBtn.SetEnabled(true)
				autoBtn.SetText("AUTO-FILL WITH CLAUDE")
				if err != nil {
					setStatus("Auto-fill failed: "+err.Error(), colOrange)
					return
				}
				how.SetText(res.HowItActs)
				beh.SetText(res.Behaviors)
				extras.SetText(strings.Join(res.Extras, "\r\n"))
				update()
				setStatus("Filled in. Edit anything you like, then copy.", colCryo)
			})
		}()
	}
	copyBtn.onClick = func() {
		if err := walk.Clipboard().SetText(out.Text()); err != nil {
			setStatus("Couldn't copy. Select the text and press Ctrl+C.", colOrange)
			return
		}
		setStatus("Copied. Paste it into Word.", colCryo)
	}
	clearBtn.onClick = func() {
		for _, e := range []*walk.LineEdit{gear, thing, source} {
			e.SetText("")
		}
		for _, e := range []*walk.TextEdit{how, beh, extras} {
			e.SetText("")
		}
		update()
		gear.SetFocus()
	}

	field := SolidColorBrush{Color: colField}
	big := Font{Family: "Segoe UI", PointSize: 12, Bold: true}
	body := Font{Family: "Segoe UI", PointSize: 10}
	input := func(assign **walk.LineEdit, cue string) Widget {
		return LineEdit{AssignTo: assign, Font: big, CueBanner: cue, Background: field, TextColor: colText, OnTextChanged: update}
	}
	box := func(assign **walk.TextEdit, h int) Widget {
		return TextEdit{AssignTo: assign, MinSize: Size{Height: h}, VScroll: true, Font: body, Background: field, TextColor: colText, OnTextChanged: update}
	}

	err := MainWindow{
		AssignTo:   &mw,
		Title:      "Gear Prompt Forge",
		MinSize:    Size{Width: 780, Height: 680},
		Size:       Size{Width: 1000, Height: 860},
		Font:       body,
		Background: SolidColorBrush{Color: colBG},
		Layout:     VBox{Margins: Margins{Left: 16, Top: 10, Right: 16, Bottom: 14}, Spacing: 8},
		Children: []Widget{
			header(),
			Composite{
				Background: SolidColorBrush{Color: colBG},
				Layout:     HBox{MarginsZero: true, Spacing: 8, Alignment: AlignHNearVNear},
				Children: []Widget{
					fieldCol("GEAR TYPE", input(&gear, "Laser Rifle")),
					joiner("based on", 92),
					fieldCol("WEAPON OR OBJECT/THING", input(&thing, "Brimstone")),
					joiner("from", 56),
					fieldCol("SOURCE MATERIAL", input(&source, "The Binding of Isaac")),
				},
			},
			Composite{
				Background: SolidColorBrush{Color: colBG},
				Layout:     HBox{MarginsZero: true, Spacing: 12},
				Children: []Widget{
					autoBtn.widget(270),
					Label{Text: "API key (optional if Claude Code is installed):", TextColor: colMuted},
					LineEdit{AssignTo: &keyEdit, PasswordMode: true, CueBanner: "sk-ant-...", Text: loadKey(), Background: field, TextColor: colText},
				},
			},
			sectionLabel("HOW IT ACTS"),
			box(&how, 44),
			sectionLabel("BEHAVIORS IT NEEDS"),
			box(&beh, 44),
			sectionLabel("EXTRA * BULLETS (ONE PER LINE)"),
			box(&extras, 60),
			sectionLabel("YOUR PROMPT"),
			TextEdit{AssignTo: &out, ReadOnly: true, VScroll: true, StretchFactor: 4, Font: body, Background: SolidColorBrush{Color: colPanel}, TextColor: colText},
			Composite{
				Background: SolidColorBrush{Color: colBG},
				Layout:     HBox{MarginsZero: true, Spacing: 12},
				Children: []Widget{
					copyBtn.widget(200),
					clearBtn.widget(120),
					Label{AssignTo: &status, TextColor: colText, Font: Font{Family: "Segoe UI", PointSize: 10, Bold: true}},
					HSpacer{},
				},
			},
		},
	}.Create()
	if err != nil {
		walk.MsgBox(nil, "Gear Prompt Forge", err.Error(), walk.MsgBoxIconError)
		return
	}
	// Icon group 2 is embedded by build.sh (rsrc: 1 = manifest, 2 = icon).
	if ic, err := walk.NewIconFromResourceId(2); err == nil {
		mw.SetIcon(ic)
	}
	for _, b := range []*lootButton{autoBtn, copyBtn, clearBtn} {
		b.cw.SetCursor(walk.CursorHand())
	}
	update()
	mw.Run()
}
