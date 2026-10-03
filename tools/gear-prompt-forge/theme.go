package main

// Borderlands-style look: dark moon-base panels, hazard stripes, cel-shaded
// outlined title text and chunky yellow buttons, all drawn with GDI.

import (
	_ "embed"
	"unsafe"

	"github.com/lxn/walk"
	. "github.com/lxn/walk/declarative"
	"github.com/lxn/win"
	"golang.org/x/sys/windows"
)

//go:embed assets/Bangers-Regular.ttf
var bangersTTF []byte

var (
	colBG      = walk.RGB(0x16, 0x19, 0x20) // space
	colPanel   = walk.RGB(0x22, 0x27, 0x31) // moon-base metal
	colField   = walk.RGB(0x0d, 0x0f, 0x13)
	colText    = walk.RGB(0xf2, 0xf2, 0xee)
	colMuted   = walk.RGB(0xa8, 0xae, 0xbb)
	colYellow  = walk.RGB(0xff, 0xc4, 0x0e) // Borderlands yellow
	colOrange  = walk.RGB(0xff, 0x8a, 0x00) // legendary orange
	colCryo    = walk.RGB(0x6f, 0xd6, 0xff)
	colBlack   = walk.RGB(0, 0, 0)
	colDisable = walk.RGB(0x6b, 0x70, 0x7a)

	gdi32        = windows.NewLazySystemDLL("gdi32.dll")
	procPolygon  = gdi32.NewProc("Polygon")
	procAddFontM = gdi32.NewProc("AddFontMemResourceEx")
	procSolidBr  = gdi32.NewProc("CreateSolidBrush")
)

const display = "Bangers"

// loadFonts registers the embedded Bangers font for this process only.
// Falls back to Impact if it can't be registered.
func loadFonts() string {
	var n uint32
	if len(bangersTTF) > 0 {
		h, _, _ := procAddFontM.Call(uintptr(unsafe.Pointer(&bangersTTF[0])), uintptr(len(bangersTTF)), 0, uintptr(unsafe.Pointer(&n)))
		if h != 0 {
			return display
		}
	}
	return "Impact"
}

var displayFamily = "Impact"

func mustFont(family string, size int, style walk.FontStyle) *walk.Font {
	f, err := walk.NewFont(family, size, style)
	if err != nil {
		f, _ = walk.NewFont("Segoe UI", size, style)
	}
	return f
}

// fillPoly fills a polygon (pixel coordinates) with a solid color.
func fillPoly(c *walk.Canvas, col walk.Color, pts []walk.Point) {
	hdc := c.HDC()
	hb, _, _ := procSolidBr.Call(uintptr(col))
	brush := win.HBRUSH(hb)
	oldB := win.SelectObject(hdc, win.HGDIOBJ(brush))
	oldP := win.SelectObject(hdc, win.GetStockObject(win.NULL_PEN))
	wp := make([]win.POINT, len(pts))
	for i, p := range pts {
		wp[i] = win.POINT{X: int32(p.X), Y: int32(p.Y)}
	}
	procPolygon.Call(uintptr(hdc), uintptr(unsafe.Pointer(&wp[0])), uintptr(len(wp)))
	win.SelectObject(hdc, oldP)
	win.SelectObject(hdc, oldB)
	win.DeleteObject(win.HGDIOBJ(brush))
}

func fillRect(c *walk.Canvas, col walk.Color, r walk.Rectangle) {
	fillPoly(c, col, []walk.Point{{X: r.X, Y: r.Y}, {X: r.X + r.Width, Y: r.Y}, {X: r.X + r.Width, Y: r.Y + r.Height}, {X: r.X, Y: r.Y + r.Height}})
}

// outlinedText draws comic-style text with a thick black outline and drop shadow.
func outlinedText(c *walk.Canvas, text string, font *walk.Font, col walk.Color, r walk.Rectangle, format walk.DrawTextFormat, o int) {
	sh := r
	sh.X += o + 1
	sh.Y += o + 1
	c.DrawTextPixels(text, font, colBlack, sh, format)
	for dx := -o; dx <= o; dx++ {
		for dy := -o; dy <= o; dy++ {
			if dx == 0 && dy == 0 {
				continue
			}
			rr := r
			rr.X += dx
			rr.Y += dy
			c.DrawTextPixels(text, font, colBlack, rr, format)
		}
	}
	c.DrawTextPixels(text, font, col, r, format)
}

func scale(w walk.Widget, v int) int {
	return v * w.DPI() / 96
}

// header paints the title banner.
func header() Widget {
	var cw *walk.CustomWidget
	return CustomWidget{
		AssignTo:            &cw,
		MinSize:             Size{Height: 96},
		MaxSize:             Size{Height: 96},
		InvalidatesOnResize: true,
		PaintMode:           PaintBuffered,
		PaintPixels: func(c *walk.Canvas, _ walk.Rectangle) error {
			b := cw.ClientBoundsPixels()
			s := func(v int) int { return scale(cw, v) }
			fillRect(c, colBG, b)
			// slanted panel
			fillPoly(c, colBlack, []walk.Point{{X: 0, Y: s(6)}, {X: b.Width - s(40), Y: s(6)}, {X: b.Width - s(70), Y: b.Height - s(4)}, {X: 0, Y: b.Height - s(4)}})
			fillPoly(c, colPanel, []walk.Point{{X: 0, Y: s(9)}, {X: b.Width - s(46), Y: s(9)}, {X: b.Width - s(74), Y: b.Height - s(8)}, {X: 0, Y: b.Height - s(8)}})
			// hazard stripes on the right
			x0 := b.Width - s(230)
			fillPoly(c, colYellow, []walk.Point{{X: x0, Y: s(9)}, {X: b.Width - s(46), Y: s(9)}, {X: b.Width - s(74), Y: b.Height - s(8)}, {X: x0 - s(28), Y: b.Height - s(8)}})
			h := b.Height - s(17)
			for x := x0 - s(28) + h; x < b.Width+h; x += s(36) {
				fillPoly(c, colBlack, []walk.Point{{X: x, Y: s(9)}, {X: x + s(16), Y: s(9)}, {X: x + s(16) - h, Y: b.Height - s(8)}, {X: x - h, Y: b.Height - s(8)}})
			}
			// re-cut the slanted right edge
			fillPoly(c, colBG, []walk.Point{{X: b.Width - s(46), Y: 0}, {X: b.Width, Y: 0}, {X: b.Width, Y: b.Height}, {X: b.Width - s(74), Y: b.Height}})
			fillPoly(c, colBlack, []walk.Point{{X: b.Width - s(46), Y: s(6)}, {X: b.Width - s(40), Y: s(6)}, {X: b.Width - s(70), Y: b.Height - s(4)}, {X: b.Width - s(76), Y: b.Height - s(4)}})
			// orange accent bar
			fillRect(c, colOrange, walk.Rectangle{X: 0, Y: b.Height - s(8), Width: b.Width - s(74), Height: s(4)})

			title := mustFont(displayFamily, 34, 0)
			defer title.Dispose()
			sub := mustFont("Segoe UI", 9, walk.FontBold)
			defer sub.Dispose()
			outlinedText(c, "GEAR PROMPT FORGE", title, colYellow, walk.Rectangle{X: s(18), Y: s(10), Width: b.Width, Height: s(54)}, walk.TextLeft|walk.TextVCenter|walk.TextSingleLine, s(3))
			ver := "DEV BUILD"
			if version != "dev" {
				ver = "V" + version
			}
			c.DrawTextPixels("BORDERLANDS: THE PRE-SEQUEL  //  LOOT PROMPT FABRICATOR  //  "+ver, sub, colMuted, walk.Rectangle{X: s(22), Y: s(62), Width: b.Width, Height: s(20)}, walk.TextLeft|walk.TextVCenter|walk.TextSingleLine)
			return nil
		},
	}
}

// sectionLabel is a yellow comic-font label.
func sectionLabel(text string) Widget {
	return Label{Text: text, TextColor: colYellow, Font: Font{Family: displayFamily, PointSize: 13}}
}

// lootButton is a chunky, outlined, slanted Borderlands-style button.
type lootButton struct {
	cw      *walk.CustomWidget
	text    string
	col     walk.Color
	enabled bool
	pressed bool
	onClick func()
}

func (lb *lootButton) SetEnabled(on bool) { lb.enabled = on; lb.cw.Invalidate() }
func (lb *lootButton) SetText(t string)   { lb.text = t; lb.cw.Invalidate() }

func (lb *lootButton) widget(width int) Widget {
	lb.enabled = true
	return CustomWidget{
		AssignTo:            &lb.cw,
		MinSize:             Size{Width: width, Height: 44},
		MaxSize:             Size{Width: width, Height: 44},
		InvalidatesOnResize: true,
		PaintMode:           PaintBuffered,
		PaintPixels: func(c *walk.Canvas, _ walk.Rectangle) error {
			b := lb.cw.ClientBoundsPixels()
			s := func(v int) int { return scale(lb.cw, v) }
			fillRect(c, colBG, b)
			off := s(4)
			if lb.pressed {
				off = s(1)
			}
			sl := s(10)
			w, h := b.Width-s(5), b.Height-s(5)
			px := s(4) - off
			py := s(4) - off
			// shadow
			fillPoly(c, colBlack, []walk.Point{{X: sl + s(4), Y: s(4)}, {X: b.Width, Y: s(4)}, {X: b.Width - sl, Y: b.Height}, {X: s(4), Y: b.Height}})
			// outline + face
			fillPoly(c, colBlack, []walk.Point{{X: px + sl, Y: py}, {X: px + w, Y: py}, {X: px + w - sl, Y: py + h}, {X: px, Y: py + h}})
			face := lb.col
			if !lb.enabled {
				face = colDisable
			}
			t := s(2)
			fillPoly(c, face, []walk.Point{{X: px + sl + t, Y: py + t}, {X: px + w - t, Y: py + t}, {X: px + w - sl - t, Y: py + h - t}, {X: px + t, Y: py + h - t}})
			f := mustFont(displayFamily, 15, 0)
			defer f.Dispose()
			c.DrawTextPixels(lb.text, f, colBlack, walk.Rectangle{X: px, Y: py, Width: w, Height: h}, walk.TextCenter|walk.TextVCenter|walk.TextSingleLine)
			return nil
		},
		OnMouseDown: func(x, y int, button walk.MouseButton) {
			if button == walk.LeftButton && lb.enabled {
				lb.pressed = true
				lb.cw.Invalidate()
			}
		},
		OnMouseUp: func(x, y int, button walk.MouseButton) {
			was := lb.pressed
			lb.pressed = false
			lb.cw.Invalidate()
			b := lb.cw.ClientBoundsPixels()
			inside := x >= 0 && y >= 0 && x < b.Width && y < b.Height
			if was && inside && lb.enabled && lb.onClick != nil {
				lb.onClick()
			}
		},
	}
}

// joiner draws the fixed "based on" / "from" words between the input boxes.
func joiner(text string, width int) Widget {
	var cw *walk.CustomWidget
	return CustomWidget{
		AssignTo:            &cw,
		MinSize:             Size{Width: width, Height: joinerH},
		MaxSize:             Size{Width: width, Height: joinerH},
		InvalidatesOnResize: true,
		PaintMode:           PaintBuffered,
		PaintPixels: func(c *walk.Canvas, _ walk.Rectangle) error {
			b := cw.ClientBoundsPixels()
			fillRect(c, colBG, b)
			f := mustFont(displayFamily, 17, 0)
			defer f.Dispose()
			// center on the input box, which sits under its label
			r := walk.Rectangle{X: 0, Y: scale(cw, joinerTop) - scale(cw, joinerNudge), Width: b.Width, Height: b.Height - scale(cw, joinerTop)}
			outlinedText(c, text, f, colCryo, r, walk.TextCenter|walk.TextVCenter|walk.TextSingleLine, scale(cw, 2))
			return nil
		},
	}
}

const (
	joinerH     = 52
	joinerTop   = 24
	joinerNudge = 8
)

// fieldCol stacks a section label over its input box.
func fieldCol(label string, input Widget) Widget {
	return Composite{
		Background:    SolidColorBrush{Color: colBG},
		StretchFactor: 100,
		Layout:        VBox{MarginsZero: true, Spacing: 4},
		Children:      []Widget{sectionLabel(label), input},
	}
}
