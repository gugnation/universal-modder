"""Offline tests for the pieces that don't need a game, a GPU or a fal key.

    uv run --with pytest pytest -q
"""
import json
import struct
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from um import fal, llm, publish, scan, sprite, video  # noqa: E402


# --------------------------------------------------------------------------- scan

def make(root: Path, files: dict):
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data if isinstance(data, bytes) else data.encode())


def engine_of(tmp_path, files):
    make(tmp_path, files)
    hits, _ = scan.detect(scan.Index(tmp_path))
    return hits[0][0], hits[0][3]


def test_unity_mono_and_version(tmp_path):
    key, det = engine_of(tmp_path, {
        "UnityPlayer.dll": b"MZ", "Game_Data/Managed/Assembly-CSharp.dll": b"MZ",
        "Game_Data/globalgamemanagers": b"\0" * 20 + b"2022.3.21f1\0" + b"\0" * 100,
        "Game_Data/app.info": "Studio\nCoolGame",
    })
    assert key == "unity-mono"
    assert det["version"] == "2022.3.21f1" and det["product"] == "CoolGame"


def test_unity_il2cpp(tmp_path):
    key, _ = engine_of(tmp_path, {"UnityPlayer.dll": b"MZ", "GameAssembly.dll": b"MZ",
                                  "Game_Data/il2cpp_data/Metadata/global-metadata.dat": b"\xaf\x1b\xb1\xfa"})
    assert key == "unity-il2cpp"


def test_unreal_version_from_exe(tmp_path):
    exe = b"MZ" + b"\0" * 5000 + "++UE5+Release-5.3".encode("utf-16-le") + b"\0" * 100
    key, det = engine_of(tmp_path, {"Proj/Binaries/Win64/Proj-Win64-Shipping.exe": exe, "Proj/Content/Paks/Proj-Windows.pak": b"x",
                                    "Proj/Content/Paks/Proj-Windows.utoc": b"x"})
    assert key == "unreal" and det["engine_version"] == "UE5+Release-5.3" and det["iostore"]


def test_godot_pck(tmp_path):
    key, det = engine_of(tmp_path, {"game.exe": b"MZ", "game.pck": b"GDPC" + struct.pack("<4I", 2, 4, 2, 1)})
    assert key == "godot" and det["version"].startswith("4.2.1")


def test_gamemaker_and_rpgmaker(tmp_path):
    assert engine_of(tmp_path / "a", {"data.win": b"FORM\0\0\0\0GEN8\0\0\0\0\0\x11"})[0] == "gamemaker"
    assert engine_of(tmp_path / "b", {"www/js/rpg_core.js": "//", "Game.exe": b"MZ"})[0] == "rpgmaker-mvmz"


def test_managed_pe(tmp_path):
    # minimal PE32 with a CLR header directory entry
    pe = bytearray(1024)
    pe[0:2] = b"MZ"
    struct.pack_into("<I", pe, 0x3C, 0x80)
    pe[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", pe, 0x84, 0x14C)
    opt = 0x80 + 24
    struct.pack_into("<H", pe, opt, 0x10B)
    struct.pack_into("<I", pe, opt + 96 + 14 * 8, 0x2000)
    p = tmp_path / "Game.exe"
    p.write_bytes(bytes(pe))
    assert scan.pe_info(p) == {"arch": "x86", "managed": True}


def test_vdf():
    d = scan._vdf('"AppState" { "appid" "105600" "name" "Terraria" "installdir" "Terraria" }')
    assert d["AppState"]["installdir"] == "Terraria"


# --------------------------------------------------------------------------- sprite

def sprite_on_white(w=64, h=48):
    im = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    for x in range(20, 40):
        for y in range(10, 30):
            im.putpixel((x, y), (200, 30, 30, 255))
    im.putpixel((30, 20), (255, 255, 255, 255))   # an interior white "eye" must survive
    return im


def test_cutout_keeps_interior_white():
    out = sprite.cutout(sprite_on_white())
    assert out.size == (20, 20)
    assert out.getpixel((10, 10))[3] == 255          # the interior white pixel is still opaque
    assert out.getpixel((0, 0))[:3] == (200, 30, 30)


def test_fit_and_hard_alpha():
    f = sprite.fit(sprite.cutout(sprite_on_white()), 10, 10, anchor="bottom")
    assert f.size == (10, 10) and f.getbbox()[3] == 10
    assert set(sprite.hard_alpha(f).getchannel("A").getdata()) <= {0, 255}


def test_sheet_slice_roundtrip():
    frames = [Image.new("RGBA", (8, 8), (i * 40, 0, 0, 255)) for i in range(5)]
    sh = sprite.sheet(frames, cols=3)
    assert sh.size == (24, 16)
    assert len(sprite.slice_sheet(sh, 8, 8)) == 5


def test_team_mask():
    im = Image.new("RGBA", (4, 1), (0, 0, 0, 255))
    im.putpixel((0, 0), (20, 60, 240, 255))            # saturated blue -> player colour
    im.putpixel((1, 0), (200, 200, 200, 255))          # grey stays
    rgb, mask = sprite.team_mask(im)
    assert mask.getpixel((0, 0)) > 200 and mask.getpixel((1, 0)) == 0


def test_seamless_edges_match():
    import numpy as np
    ramp = np.tile(np.linspace(0, 255, 64)[None, :, None], (64, 1, 4)).astype(np.uint8)   # huge seam at the wrap
    ramp[..., 3] = 255
    out = np.asarray(sprite.seamless(Image.fromarray(ramp))).astype(int)
    before = np.abs(ramp[:, 0, :3].astype(int) - ramp[:, -1, :3].astype(int)).mean()
    after = np.abs(out[:, 0, :3] - out[:, -1, :3]).mean()
    assert before > 200 and after < 12


# --------------------------------------------------------------------------- fal (offline parts)

def test_kv_and_urls(tmp_path):
    assert fal._kv(["prompt=a cat", "num_images:=2", "flag:=true"]) == {"prompt": "a cat", "num_images": 2, "flag": True}
    res = {"images": [{"url": "https://v3.fal.media/a.png", "content_type": "image/png"}, {"url": "https://v3.fal.media/b.png"}],
           "mask_image": {"url": "https://v3.fal.media/m.png"}}
    assert [u for _, u, _ in fal._urls_in(res)] == ["https://v3.fal.media/a.png", "https://v3.fal.media/b.png", "https://v3.fal.media/m.png"]


# --------------------------------------------------------------------------- publish

def test_publish_check(tmp_path, capsys):
    # fixtures assembled at runtime so this file doesn't trip the toolkit's own publish check
    fake_key = "FAL" + "_KEY=" + "abcdefghijklmnopqrstuvwxyz0123"
    ghidra_name = "FUN" + "_00401000"
    make(tmp_path / "mod", {"src/Mod.cs": f"int {ghidra_name}();\n// " + "Decompiled with ILSpy", "README.md": "My mod, built with dnSpy notes",
                            "config.txt": fake_key})
    make(tmp_path / "game", {"data/big.bin": b"x" * 4096})
    (tmp_path / "mod" / "copied.bin").write_bytes(b"x" * 4096)
    assert publish.check(str(tmp_path / "mod"), str(tmp_path / "game")) == 1
    out = capsys.readouterr().out
    assert "game file copied verbatim" in out and "FAL_KEY assignment" in out and "Ghidra auto-name" in out
    assert "decompiler header x1 in src/Mod.cs" in out and "README.md" not in out.split("decompiler header")[-1].split("\n")[0]


# --------------------------------------------------------------------------- video

@pytest.mark.skipif(subprocess.run(["which", "ffmpeg"], capture_output=True).returncode, reason="needs ffmpeg")
def test_compile_small_edl(tmp_path):
    for i, color in enumerate(["red", "blue"]):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=640x360:d=3:r=30", "-f", "lavfi", "-i", "sine=f=440:d=3",
                        "-shortest", str(tmp_path / f"c{i}.mp4")], check=True)
    edl = {"size": [640, 360], "fps": 30, "bpm": 120, "beat_lock": True, "transition": {"type": "cut"},
           "segments": [{"clip": "c0.mp4", "in": 0, "beats": 4, "hook": "Hello"},
                        {"clip": "c1.mp4", "in": 0.5, "beats": 4, "title": "A title", "credit": "@someone", "transition": {"type": "fade", "duration": 0.3}},
                        {"card": {"title": "The end"}, "dur": 1.5}]}
    (tmp_path / "edl.json").write_text(json.dumps(edl))
    video.compile_edl(tmp_path / "edl.json", str(tmp_path / "out.mp4"))
    info = video.probe(tmp_path / "out.mp4")
    assert abs(info["duration"] - (2 + 2 + 1.5)) < 0.15 and info["audio"]


# --------------------------------------------------------------------------- llm

HW_PC = dict(ram_gb=128, vram_gb=24, budget_gb=128 + 24 - llm.HEADROOM_GB, gpus=[{"name": "x", "vram_gb": 24}])


def test_quant_labels_and_grouping():
    G = 1 << 30
    files = [dict(path=p, size=s * G) for p, s in [
        ("UD-Q2_K_XL/GLM-5.3-Flash-UD-Q2_K_XL-00002-of-00003.gguf", 40),
        ("UD-Q2_K_XL/GLM-5.3-Flash-UD-Q2_K_XL-00001-of-00003.gguf", 40),
        ("UD-Q2_K_XL/GLM-5.3-Flash-UD-Q2_K_XL-00003-of-00003.gguf", 35),
        ("GLM-5.3-Flash-IQ1_M.gguf", 72), ("GLM-5.3-Flash-Q4_K_M-00001-of-00004.gguf", 50),
        ("GLM-5.3-Flash-Q4_K_M-00002-of-00004.gguf", 50), ("GLM-5.3-Flash-Q4_K_M-00003-of-00004.gguf", 50),
        ("GLM-5.3-Flash-Q4_K_M-00004-of-00004.gguf", 45), ("mmproj-F16.gguf", 1), ("README.md", 0)]]
    files[0]["lfs"] = {"size": 40 * G}
    qs = llm.group_quants(files)
    assert [(q["quant"], q["size_gb"], len(q["files"])) for q in qs] == [
        ("IQ1_M", 72, 1), ("UD-Q2_K_XL", 115, 3), ("Q4_K_M", 195, 4)]
    assert qs[1]["files"][0].endswith("00001-of-00003.gguf")
    assert llm.quant_label("x/model.Q8_0.gguf") == "Q8_0" and llm.quant_label("m-BF16.gguf") == "BF16"


def test_fit_and_pick():
    assert llm.fit(10, HW_PC) == "gpu" and llm.fit(115, HW_PC) == "ram+gpu"
    assert llm.fit(195, HW_PC) == "disk-paged" and llm.fit(400, HW_PC) == "no"
    assert llm.fit(20, dict(HW_PC, vram_gb=0, budget_gb=26)) == "ram"
    qs = [dict(quant=q, size_gb=s, files=[f"m-{q}.gguf"], fits=llm.fit(s, HW_PC)) for q, s in
          [("IQ1_M", 72), ("UD-Q2_K_XL", 115), ("Q4_K_M", 195)]]
    assert llm.pick(qs)["quant"] == "UD-Q2_K_XL"
    assert llm.pick(qs, "q4_k_m")["quant"] == "Q4_K_M" and llm.pick(qs, "Q6_K") is None
    assert llm.pick([dict(q, fits="no") for q in qs]) is None


def test_server_cmd_offloads_experts_only_when_needed(tmp_path):
    g = tmp_path / "m.gguf"
    big = llm.server_cmd("llama-server", g, 115, HW_PC, 8192, 8080, "127.0.0.1")
    small = llm.server_cmd("llama-server", g, 10, HW_PC, 8192, 8080, "127.0.0.1", ["-t", "8"])
    assert "--cpu-moe" in big and "-ngl" in big and "--jinja" in big
    assert "--cpu-moe" not in small and small[-2:] == ["-t", "8"]
    if not llm.is_mac():
        assert "-ngl" not in llm.server_cmd("llama-server", g, 10, dict(HW_PC, vram_gb=0), 8192, 8080, "h")


def test_first_gguf_and_split_size(tmp_path):
    for i in (1, 2):
        (tmp_path / f"m-Q2_K-0000{i}-of-00002.gguf").write_bytes(b"x" * (10 * i))
    (tmp_path / "mmproj-F16.gguf").write_bytes(b"y")
    first = llm.first_gguf(str(tmp_path))
    assert first.name == "m-Q2_K-00001-of-00002.gguf" and llm.model_bytes(first) == 30


def test_hf_tree_pagination_and_resumable_download(tmp_path, monkeypatch):
    import http.server
    import threading

    blob = bytes(range(256)) * 4096  # 1 MiB
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            seen.append((self.path, self.headers.get("Authorization")))
            base = f"http://127.0.0.1:{self.server.server_port}"
            if self.path.startswith("/api/models/o/r/tree/main"):
                page2 = "cursor=2" in self.path
                files = [dict(type="file", path=("b-Q2_K.gguf" if page2 else "a-Q8_0.gguf"),
                              size=len(blob), lfs={"size": len(blob)}), dict(type="directory", path="d")]
                body = json.dumps(files).encode()
                self.send_response(200)
                if not page2:
                    self.send_header("Link", f'<{base}/api/models/o/r/tree/main?recursive=true&cursor=2>; rel="next"')
            elif self.path.startswith("/o/r/resolve/"):
                self.send_response(302)
                self.send_header("Location", f"{base}/cdn/blob")
                self.end_headers()
                return
            elif self.path == "/cdn/blob":
                start = int((self.headers.get("Range") or "bytes=0-")[6:-1])
                if start == 0:  # first attempt: drop the connection halfway
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(blob)))
                    self.end_headers()
                    self.wfile.write(blob[:len(blob) // 2])
                    self.wfile.flush()
                    self.connection.shutdown(2)
                    return
                body = blob[start:]
                self.send_response(206)
            else:
                self.send_response(404)
                body = b"{}"
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(llm, "HF", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    monkeypatch.setenv("HF_TOKEN", "hf_secret")
    try:
        files = llm.tree("o/r")
        assert [f["path"] for f in files] == ["a-Q8_0.gguf", "b-Q2_K.gguf"]
        dest = tmp_path / "a-Q8_0.gguf"
        llm.download("o/r", "a-Q8_0.gguf", dest, len(blob))
        assert dest.read_bytes() == blob and not dest.with_name(dest.name + ".part").exists()
    finally:
        srv.shutdown()
    assert all(auth == "Bearer hf_secret" for p, auth in seen if not p.startswith("/cdn"))
    assert all(auth is None for p, auth in seen if p.startswith("/cdn"))  # token never sent to the CDN
    assert sum(p == "/cdn/blob" for p, _ in seen) >= 2  # it resumed
