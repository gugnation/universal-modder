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

from um import cli, fal, mint, publish, scan, sprite, video  # noqa: E402


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


# --------------------------------------------------------------------------- mint (against a local mock of the API)

class MockMint:
    """Tiny stand-in for api.mint.gg: routes[(method, path)] = [(status, headers, body), ...] served in order
    (the last one repeats). Every request is logged with its headers and JSON body."""

    def __init__(self):
        import http.server
        import threading
        self.routes, self.log = {}, []
        mock = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _serve(self):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                mock.log.append(dict(method=self.command, path=self.path, headers=dict(self.headers.items()),
                                     body=json.loads(raw) if raw else None))
                queue = mock.routes.get((self.command, self.path.split("?")[0]))
                status, headers, body = (queue.pop(0) if len(queue) > 1 else queue[0]) if queue else (404, {}, {"title": "not found"})
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            do_GET = do_POST = do_DELETE = _serve

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        self.api = f"http://127.0.0.1:{self.port}/v1"
        self.cdn = f"http://localhost:{self.port}/cdn"      # another origin: must never see the key
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def on(self, method, path, *responses):
        self.routes[(method, "/v1" + path if not path.startswith("/cdn") else path)] = list(responses)

    def calls(self, method, path):
        return [r for r in self.log if r["method"] == method and r["path"].split("?")[0].endswith(path)]


@pytest.fixture
def mock_mint(monkeypatch, tmp_path):
    import urllib.request
    m = MockMint()
    monkeypatch.setenv("MINT_API_BASE_URL", m.api)
    monkeypatch.setenv("MINT_API_KEY", "test-mint-key")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mint, "_urlopen", urllib.request.build_opener(urllib.request.ProxyHandler({})).open)
    monkeypatch.setattr(mint, "_sleep", lambda s: None)
    yield m
    m.server.shutdown()


def op(status, **kw):
    return (200, {}, {"object": "operation", "id": "op_1", "type": "model_generation", "status": status, **kw})


def test_mint_model_end_to_end(mock_mint, tmp_path):
    m = mock_mint
    m.on("POST", "/pricing:estimate", (200, {}, {"object": "pricing_estimate", "credits": {"requiredToStart": 300, "estimatedTotal": 400}}))
    m.on("GET", "/usage", (200, {}, {"object": "usage", "credits": {"totalAvailable": 5000}}))
    m.on("POST", "/models:generate", (503, {}, {"title": "busy"}), (202, {"Location": "/v1/operations/op_1"}, op("queued")[2]))
    m.on("GET", "/operations/op_1", op("running"), (200, {"Retry-After": "3"}, op("running")[2]),
         op("succeeded", resource={"type": "model", "id": "mdl_1"}))
    m.on("GET", "/assets/model/mdl_1/artifact-manifest", (200, {}, {"artifacts": [
        {"fileName": "lamp.glb", "mimeType": "model/gltf-binary", "downloadUrl": m.api + "/assets/model/mdl_1/artifacts/a1/download"},
        {"fileName": "lamp_optimized.glb", "mimeType": "model/gltf-binary", "downloadUrl": m.cdn + "/opt.glb"},
        {"fileName": "preview.png", "role": "preview", "mimeType": "image/png", "downloadUrl": m.cdn + "/p.png"}],
        "links": {"url": "https://mint.gg/models/mdl_1"}}))
    m.on("GET", "/assets/model/mdl_1/artifacts/a1/download", (302, {"Location": m.cdn + "/lamp.glb"}, b""))
    for f in ("lamp.glb", "opt.glb", "p.png"):
        m.on("GET", f"/cdn/{f}", (200, {}, b"glTF" + f.encode()))

    cli.main(["mint", "model", "A small ceramic lamp with an orange shade", "--idempotency-key", "orange-lamp",
              "--max-credits", "10000", "--out", "gen"])

    gen = m.calls("POST", "/models:generate")
    assert len(gen) == 2 and {g["headers"]["Idempotency-Key"] for g in gen} == {"orange-lamp"}   # retried with the same key
    assert gen[0]["body"] == {"prompt": "A small ceramic lamp with an orange shade", "generationPreset": "standard"}
    assert gen[0]["headers"]["Authorization"] == "Bearer test-mint-key"
    assert m.calls("POST", "/pricing:estimate")[0]["body"] == {"operation": "model_generation", "generationPreset": "standard", "generationMode": "auto"}
    cdn = [r for r in m.log if r["path"].startswith("/cdn/")]
    assert len(cdn) == 3 and not any("Authorization" in r["headers"] for r in cdn)     # the key never leaves the API origin
    stem = "a_small_ceramic_lamp_with"
    assert sorted(p.name for p in (tmp_path / "gen").iterdir()) == sorted(
        [f"{stem}.glb", f"{stem}_lamp_optimized.glb", f"{stem}_preview.png", "mint_manifest.jsonl"])
    assert (tmp_path / "gen" / f"{stem}.glb").read_bytes() == b"glTFlamp.glb"
    rec = json.loads((tmp_path / "gen" / "mint_manifest.jsonl").read_text().splitlines()[-1])
    assert rec["operation"] == "op_1" and rec["resource"]["id"] == "mdl_1" and rec["idempotency_key"] == "orange-lamp" and len(rec["files"]) == 3


def test_mint_falls_back_to_model_assets(mock_mint, tmp_path):
    m = mock_mint
    m.on("GET", "/models/mdl_2", (200, {}, {"object": "model", "id": "mdl_2", "assets": {
        "glbUrl": m.cdn + "/a.glb?sig=1", "fbxUrl": m.cdn + "/a.fbx", "previewImageUrl": m.cdn + "/a.webp", "objUrl": None}}))
    for f in ("a.glb", "a.fbx", "a.webp"):
        m.on("GET", f"/cdn/{f}", (200, {}, b"x"))
    cli.main(["mint", "files", "mdl_2", "--out", "gen", "--name", "chest", "--formats", "glb,preview"])
    assert sorted(p.name for p in (tmp_path / "gen").iterdir()) == ["chest.glb", "chest_preview.webp", "mint_manifest.jsonl"]


def test_mint_max_credits_refuses_before_starting(mock_mint, capsys):
    m = mock_mint
    m.on("POST", "/pricing:estimate", (200, {}, {"credits": {"requiredToStart": 9000, "estimatedTotal": 12000}}))
    with pytest.raises(SystemExit):
        cli.main(["mint", "model", "a lamp", "--max-credits", "10000"])
    assert "above --max-credits 10000" in capsys.readouterr().err and not m.calls("POST", "/models:generate")


def test_mint_billing_and_review_stops(mock_mint, tmp_path, capsys):
    m = mock_mint
    m.on("POST", "/models:generate", op("billing_required", billing={"reason": "insufficient_credits", "requiredCredits": 400,
                                                                     "availableCredits": 10, "actionUrl": "https://mint.gg/billing"}))
    with pytest.raises(SystemExit):
        cli.main(["mint", "model", "a lamp", "--idempotency-key", "k1"])
    err = capsys.readouterr().err
    assert "https://mint.gg/billing" in err and "--idempotency-key k1" in err

    m.on("POST", "/models:generate", op("preview_ready", generationMode="review", assets={"previewImageUrl": m.cdn + "/prev.png"}))
    m.on("GET", "/cdn/prev.png", (200, {}, b"png"))
    cli.main(["mint", "model", "a lamp", "--review", "--name", "lamp", "--out", "gen"])
    assert m.calls("POST", "/models:generate")[-1]["body"]["generationMode"] == "review"
    assert (tmp_path / "gen" / "lamp_preview.png").exists() and "um mint approve op_1" in capsys.readouterr().err
    assert not m.calls("POST", "/operations/op_1:approve")                                # never approved on its own


def test_mint_validation_error_is_readable(mock_mint, capsys):
    mock_mint.on("POST", "/models:generate", (422, {"X-Request-Id": "req_9"}, {
        "type": "https://api.mint.gg/problems/validation", "title": "Invalid request",
        "errors": [{"path": "/maxCredits", "code": "unknown_field", "message": "is not allowed"}]}))
    with pytest.raises(SystemExit):
        cli.main(["mint", "model", "a lamp", "--set", "maxCredits:=10000"])
    err = capsys.readouterr().err
    assert "/maxCredits: is not allowed" in err and "req_9" in err and "test-mint-key" not in err
    assert len(mock_mint.calls("POST", "/models:generate")) == 1                       # 4xx is never retried


def test_mint_needs_key(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("MINT_API_KEY", raising=False)
    monkeypatch.delenv("MINT_API_KEY_FILE", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mint, "__file__", str(tmp_path / "um" / "mint.py"))   # no repo .env either
    with pytest.raises(SystemExit):
        cli.main(["mint", "usage"])
    assert "MINT_API_KEY is not set" in capsys.readouterr().err


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


def test_publish_check_mint(tmp_path, capsys):
    make(tmp_path / "mod", {"README.md": "Lamp mod. Models by fal.", "assets/mint_manifest.jsonl": "{}",
                            "cfg.ini": "MINT" + "_API_KEY = " + "mint_live_abcdefghijklmnopqrstuvwxyz"})
    assert publish.check(str(tmp_path / "mod")) == 1
    out = capsys.readouterr().out
    assert "MINT_API_KEY assignment in cfg.ini" in out and "mint-generated assets" in out


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
