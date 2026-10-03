package main

import (
	"context"
	"errors"
	"os/exec"
	"strings"
	"time"
)

func hasClaudeCLI() bool {
	_, err := exec.LookPath("claude")
	return err == nil
}

// runClaudeCLI runs `claude -p` (Claude Code in print mode) with the prompt on stdin.
func runClaudeCLI(prompt string) (string, error) {
	path, err := exec.LookPath("claude")
	if err != nil {
		return "", errors.New("Claude Code isn't installed")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 4*time.Minute)
	defer cancel()
	cmd := exec.CommandContext(ctx, path, "-p", "--output-format", "text")
	cmd.Stdin = strings.NewReader(prompt)
	hideWindow(cmd)
	out, err := cmd.Output()
	if err != nil {
		if ctx.Err() != nil {
			return "", errors.New("Claude Code took too long. Try again")
		}
		return "", errors.New("Claude Code failed. Open it once to sign in, then try again")
	}
	return string(out), nil
}
