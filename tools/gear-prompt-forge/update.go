package main

// Self-update: on launch the app checks this repo's GitHub releases for a newer
// "gear-prompt-forge-v<N>" build (published by .github/workflows/gear-prompt-forge.yml),
// downloads GearPromptForge.exe, verifies its SHA-256, and swaps it in place.

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

// version is set at build time: -ldflags "-X main.version=<N>". "dev" never updates.
var version = "dev"

const (
	releasesURL = "https://api.github.com/repos/gugnation/universal-modder/releases?per_page=50"
	tagPrefix   = "gear-prompt-forge-v"
	assetName   = "GearPromptForge.exe"
)

type ghRelease struct {
	TagName    string `json:"tag_name"`
	Draft      bool   `json:"draft"`
	Prerelease bool   `json:"prerelease"`
	Assets     []struct {
		Name   string `json:"name"`
		URL    string `json:"browser_download_url"`
		Digest string `json:"digest"`
		Size   int64  `json:"size"`
	} `json:"assets"`
}

// cleanupOldExe removes the copy left behind by the previous update.
func cleanupOldExe() {
	if exe, err := os.Executable(); err == nil {
		_ = os.Remove(exe + ".old")
	}
}

// checkAndInstallUpdate returns the new version number once a newer build has
// been installed over the running exe, or 0 when there is nothing to do.
func checkAndInstallUpdate() (int, error) {
	cur, err := strconv.Atoi(version)
	if err != nil {
		return 0, nil // dev build
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()

	req, _ := http.NewRequestWithContext(ctx, "GET", releasesURL, nil)
	req.Header.Set("Accept", "application/vnd.github+json")
	req.Header.Set("User-Agent", "GearPromptForge/"+version)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return 0, fmt.Errorf("update check returned %d", resp.StatusCode)
	}
	var rels []ghRelease
	if err := json.NewDecoder(resp.Body).Decode(&rels); err != nil {
		return 0, err
	}

	best, bestURL, bestDigest := cur, "", ""
	for _, r := range rels {
		if r.Draft || r.Prerelease || !strings.HasPrefix(r.TagName, tagPrefix) {
			continue
		}
		n, err := strconv.Atoi(strings.TrimPrefix(r.TagName, tagPrefix))
		if err != nil || n <= best {
			continue
		}
		for _, a := range r.Assets {
			if a.Name == assetName {
				best, bestURL, bestDigest = n, a.URL, strings.TrimPrefix(a.Digest, "sha256:")
			}
		}
	}
	if bestURL == "" {
		return 0, nil
	}

	exe, err := os.Executable()
	if err != nil {
		return 0, err
	}
	exe, _ = filepath.EvalSymlinks(exe)
	tmp := exe + ".new"

	dreq, _ := http.NewRequestWithContext(ctx, "GET", bestURL, nil)
	dreq.Header.Set("User-Agent", "GearPromptForge/"+version)
	dresp, err := http.DefaultClient.Do(dreq)
	if err != nil {
		return 0, err
	}
	defer dresp.Body.Close()
	if dresp.StatusCode != 200 {
		return 0, fmt.Errorf("download returned %d", dresp.StatusCode)
	}
	f, err := os.Create(tmp)
	if err != nil {
		return 0, err
	}
	h := sha256.New()
	_, err = io.Copy(io.MultiWriter(f, h), dresp.Body)
	f.Close()
	if err != nil {
		os.Remove(tmp)
		return 0, err
	}
	sum := hex.EncodeToString(h.Sum(nil))
	if bestDigest != "" && !strings.EqualFold(sum, bestDigest) {
		os.Remove(tmp)
		return 0, errors.New("downloaded update failed its checksum")
	}
	if b, err := os.ReadFile(tmp); err != nil || len(b) < 2 || b[0] != 'M' || b[1] != 'Z' {
		os.Remove(tmp)
		return 0, errors.New("downloaded update isn't a Windows program")
	}

	// Windows lets a running exe be renamed, so move it aside and put the new one in place.
	_ = os.Remove(exe + ".old")
	if err := os.Rename(exe, exe+".old"); err != nil {
		os.Remove(tmp)
		return 0, err
	}
	if err := os.Rename(tmp, exe); err != nil {
		_ = os.Rename(exe+".old", exe)
		return 0, err
	}
	return best, nil
}

// relaunch starts the (updated) exe again.
func relaunch() error {
	exe, err := os.Executable()
	if err != nil {
		return err
	}
	return exec.Command(exe).Start()
}
