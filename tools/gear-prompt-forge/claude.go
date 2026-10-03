package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/anthropics/anthropic-sdk-go"
	"github.com/anthropics/anthropic-sdk-go/option"
	"github.com/anthropics/anthropic-sdk-go/shared/constant"
)

// autoFill holds what Claude writes for one gear idea.
type autoFill struct {
	HowItActs string   `json:"howItActs"`
	Behaviors string   `json:"behaviors"`
	Extras    []string `json:"extras"`
}

// configPath is where the API key is remembered (%APPDATA%\GearPromptForge\config.json).
func configPath() string {
	dir, err := os.UserConfigDir()
	if err != nil {
		return ""
	}
	return filepath.Join(dir, "GearPromptForge", "config.json")
}

func loadKey() string {
	if p := configPath(); p != "" {
		if b, err := os.ReadFile(p); err == nil {
			var c struct{ APIKey string `json:"apiKey"` }
			if json.Unmarshal(b, &c) == nil && c.APIKey != "" {
				return c.APIKey
			}
		}
	}
	return os.Getenv("ANTHROPIC_API_KEY")
}

func saveKey(key string) {
	p := configPath()
	if p == "" {
		return
	}
	_ = os.MkdirAll(filepath.Dir(p), 0o700)
	b, _ := json.Marshal(map[string]string{"apiKey": key})
	_ = os.WriteFile(p, b, 0o600)
}

func askPrompt(g, t, s string) string {
	return "You help write a prompt for a Borderlands: The Pre-Sequel mod. The user wants a " + g +
		" based on " + t + " from " + s + ".\n\n" +
		"Reply with only a JSON object: {\"howItActs\": string, \"behaviors\": string, \"extras\": string[]}.\n" +
		"- howItActs: how " + t + " actually acts in " + s + " (fire pattern, charge, projectile or beam behaviour, range, piercing, effects). One comma-separated phrase list, lowercase, no trailing period, about 25-45 words. Be accurate to the real item.\n" +
		"- behaviors: the specific behaviors the " + g + " needs to recreate it faithfully (timings, rules, visual and audio tells, synergies). Same style, about 25-45 words.\n" +
		"- extras: 3 or 4 short extra bullet points (full sentences, no leading '*') that help build THIS item in Borderlands: The Pre-Sequel. Always include one with 2 parody name ideas plus a red-text flavour line. Others can cover manufacturer, rarity, element (Fire, Shock, Corrosive, Cryo, Explosive or none), low gravity / Oz kit / butt slam interactions, and level/UVHM scaling. Only include what fits this item. Never say which boss or enemy drops it or name a dedicated drop source: drops are random.\n" +
		"Example of the style: {\"howItActs\": \"hold fire to charge, release to fire a thick blood-red beam that crosses the whole room and pierces every enemy\", \"behaviors\": \"a visible charge-up that must be full before release, the beam locks to the aim direction, rapid damage ticks on everything it touches\", \"extras\": [\"Name ideas: \\\"Hellfire Tantrum\\\" or \\\"Mom's Disappointment\\\", red text: \\\"Mama's going to be so upset.\\\"\"]}"
}

// fillIn uses the API key when one is set, otherwise the Claude Code CLI
// (your Claude account) when it is installed.
func fillIn(key, g, t, s string) (autoFill, error) {
	if key != "" {
		return askClaude(key, g, t, s)
	}
	if hasClaudeCLI() {
		raw, err := runClaudeCLI(askPrompt(g, t, s))
		if err != nil {
			return autoFill{}, err
		}
		return parseFill(raw)
	}
	return autoFill{}, errors.New("paste an Anthropic API key, or install Claude Code so the app can use your Claude account")
}

// askClaude asks Claude to fill in how the item acts, its behaviors and extra bullets.
func askClaude(key, g, t, s string) (autoFill, error) {
	var out autoFill
	client := anthropic.NewClient(option.WithAPIKey(key))
	ctx, cancel := context.WithTimeout(context.Background(), 4*time.Minute)
	defer cancel()

	resp, err := client.Beta.Messages.New(ctx, anthropic.BetaMessageNewParams{
		Model:        "claude-opus-5-5",
		MaxTokens:    16000,
		OutputConfig: anthropic.BetaOutputConfigParam{Effort: anthropic.BetaOutputConfigEffortLow},
		Fallbacks:    anthropic.BetaFallbacksParamUnion{OfDefault: constant.ValueOf[constant.Default]()},
		Betas:        []anthropic.AnthropicBeta{anthropic.AnthropicBetaServerSideFallback2026_07_01},
		Messages: []anthropic.BetaMessageParam{
			anthropic.NewBetaUserMessage(anthropic.NewBetaTextBlock(askPrompt(g, t, s))),
		},
	})
	if err != nil {
		var apierr *anthropic.Error
		if errors.As(err, &apierr) {
			switch apierr.StatusCode {
			case 401:
				return out, errors.New("the API key was rejected. Check it and try again")
			case 429:
				return out, errors.New("too many requests or out of credit. Try again later")
			case 529, 500, 502, 503:
				return out, errors.New("Claude is busy right now. Try again in a minute")
			}
			return out, fmt.Errorf("Claude returned an error (%d)", apierr.StatusCode)
		}
		return out, errors.New("couldn't reach Claude. Check your internet connection")
	}
	if resp.StopReason == anthropic.BetaStopReasonRefusal {
		return out, errors.New("Claude declined that one. Try rewording the idea")
	}

	var text strings.Builder
	for _, block := range resp.Content {
		if b, ok := block.AsAny().(anthropic.BetaTextBlock); ok {
			text.WriteString(b.Text)
		}
	}
	return parseFill(text.String())
}

func parseFill(raw string) (autoFill, error) {
	var out autoFill
	i, j := strings.Index(raw, "{"), strings.LastIndex(raw, "}")
	if i < 0 || j <= i || json.Unmarshal([]byte(raw[i:j+1]), &out) != nil {
		return out, errors.New("Claude's answer came back garbled. Try again")
	}
	out.HowItActs = strings.TrimSuffix(strings.TrimSpace(out.HowItActs), ".")
	out.Behaviors = strings.TrimSuffix(strings.TrimSpace(out.Behaviors), ".")
	kept := out.Extras[:0]
	for _, e := range out.Extras {
		l := strings.ToLower(e)
		if strings.TrimSpace(e) != "" && !strings.Contains(l, "dropped by") && !strings.Contains(l, "drops from") && !strings.Contains(l, "drop source") {
			kept = append(kept, strings.TrimSpace(e))
		}
	}
	out.Extras = kept
	return out, nil
}

