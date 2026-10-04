"""Run open-weight LLMs (GGUF) locally with llama.cpp: search Hugging Face, size them against your PC, download, serve.

    um llm hw                                   # RAM, GPU VRAM, free disk, what size of model this PC can hold
    um llm search "GLM-5.3 GGUF"                # find repos (ids, downloads, gated or not)
    um llm files huihui-ai/<repo>               # every GGUF quant in a repo, its size, and whether it fits here
    um llm get huihui-ai/<repo> [--quant Q2_K]  # download one quant (largest that fits by default), resumable
    um llm serve <dir-or-.gguf> [--ctx 16384]   # start llama-server: OpenAI-compatible API on http://127.0.0.1:8080/v1
    um llm chat "hello"                         # one-shot test against the running server

Only GGUF repos run on a normal PC. FP8 / safetensors repos are for vLLM or SGLang on datacenter GPUs
(a 320B FP8 model needs ~320 GB of GPU memory); `um llm files` says so when you point it at one.
Mixture-of-experts models (few active params, e.g. 320B total / 18B active) run acceptably with the
expert weights in system RAM and the rest on the GPU, which `serve` sets up (`--cpu-moe`) when the model
is bigger than VRAM. The budget is RAM + VRAM minus headroom; anything bigger gets paged from disk and
crawls. Under WSL, RAM is capped by .wslconfig, so run `um llm` from Windows for big models.

Gated repos: accept the terms on the model page, then set HF_TOKEN (huggingface.co/settings/tokens).
HF_ENDPOINT points it at a Hugging Face mirror, as with huggingface_hub.
Downloads go to ~/.universal-modder/models/<repo>/ unless --dir is given (or UM_MODELS is set).
llama-server comes from github.com/ggml-org/llama.cpp/releases (Windows: the -cuda- zip for NVIDIA);
put it on PATH or set UM_LLAMA_SERVER to the exe.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from um.common import data_dir, die, emit, is_mac, is_windows, is_wsl

HF = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")  # HF_ENDPOINT: a mirror
GB = 1024 ** 3
HEADROOM_GB = 6  # OS, KV cache for a modest context, compute buffers

SPLIT = re.compile(r"-(\d{5})-of-(\d{5})\.gguf$", re.I)
QUANT = re.compile(r"(UD-)?(I?Q\d_[0-9A-Z]+(?:_[A-Z]+)?|Q\d_\d|TQ\d_\d|MXFP4(?:_MOE)?|BF16|F16|F32|FP16)", re.I)


# --------------------------------------------------------------------------- hardware

def _ram_bytes() -> int:
    if is_windows():
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return int(m.ullTotalPhys)
    if is_mac():
        out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout
        return int(out.strip() or 0)
    try:
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def _gpus() -> list[dict]:
    smi = shutil.which("nvidia-smi") or shutil.which("nvidia-smi.exe")
    if not smi:
        return []
    try:
        out = subprocess.run([smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    gpus = []
    for line in out.strip().splitlines():
        name, _, mib = line.rpartition(",")
        if mib.strip().isdigit():
            gpus.append(dict(name=name.strip(), vram_gb=round(int(mib) / 1024, 1)))
    return gpus


def hardware(models_dir: Path | None = None) -> dict:
    ram = _ram_bytes() / GB
    gpus = _gpus()
    vram = sum(g["vram_gb"] for g in gpus)
    d = models_dir or _models_root()
    probe = d if d.exists() else Path(d.anchor or "/")
    free = shutil.disk_usage(probe).free / GB
    if is_mac():
        # unified memory: the GPU can use most of it, so don't count it twice
        vram = 0
    budget = max(ram + vram - HEADROOM_GB, 0)
    notes = []
    if is_wsl():
        notes.append("WSL: RAM shown is the WSL VM's cap (.wslconfig), not the PC's; run um llm from Windows for big models")
    if not gpus and not is_mac():
        notes.append("no NVIDIA GPU found: llama.cpp will run on CPU only (works, slower)")
    return dict(ram_gb=round(ram, 1), gpus=gpus, vram_gb=round(vram, 1), budget_gb=round(budget, 1),
                free_disk_gb=round(free, 1), models_dir=str(d), notes=notes)


def fit(size_gb: float, hw: dict) -> str:
    if hw["vram_gb"] and size_gb + 2 <= hw["vram_gb"]:
        return "gpu"            # all on the GPU: fast
    if size_gb <= hw["budget_gb"]:
        return "ram+gpu" if hw["vram_gb"] else "ram"
    if size_gb <= hw["budget_gb"] * 1.5:
        return "disk-paged"     # mmap pages weights from disk on every token: very slow
    return "no"


# --------------------------------------------------------------------------- hugging face

def _req(url: str, token: bool = True) -> urllib.request.Request:
    r = urllib.request.Request(url, headers={"User-Agent": "universal-modder"})
    tok = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if token and tok:
        # unredirected: the token goes to huggingface.co only, never to the CDN a download redirects to
        r.add_unredirected_header("Authorization", f"Bearer {tok}")
    return r


def _get_json(url: str):
    try:
        with urllib.request.urlopen(_req(url), timeout=60) as resp:
            return json.load(resp), resp.headers.get("Link", "")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            die(f"{e.code} from Hugging Face: the repo is gated or private. Accept its terms on the model page, "
                f"then set HF_TOKEN (huggingface.co/settings/tokens)")
        if e.code == 404:
            die(f"not found on Hugging Face: {url.split('/api/models/')[-1].split('/tree')[0]} "
                f"(check the exact repo id with `um llm search`)")
        die(f"Hugging Face {e.code}: {url}")
    except urllib.error.URLError as e:
        die(f"can't reach huggingface.co: {e.reason}")


def search(query: str, limit: int = 30) -> list[dict]:
    q = urllib.parse.urlencode(dict(search=query, limit=limit, sort="downloads", direction=-1, full="false"))
    data, _ = _get_json(f"{HF}/api/models?{q}")
    return [dict(id=m["id"], downloads=m.get("downloads", 0), likes=m.get("likes", 0),
                 gated=m.get("gated") or False, gguf="gguf" in (m.get("tags") or []) or "gguf" in m["id"].lower())
            for m in data]


def tree(repo: str, rev: str = "main") -> list[dict]:
    url = f"{HF}/api/models/{repo}/tree/{rev}?recursive=true"
    out = []
    while url:
        data, link = _get_json(url)
        out += [f for f in data if f.get("type") == "file"]
        m = re.search(r'<([^>]+)>;\s*rel="next"', link or "")
        url = m.group(1) if m else None
    return out


def _size(f: dict) -> int:
    return int((f.get("lfs") or {}).get("size") or f.get("size") or 0)


def quant_label(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    hits = QUANT.findall(name) or QUANT.findall(path)
    if not hits:
        return Path(SPLIT.sub(".gguf", name)).stem
    pre, q = hits[-1]
    return (pre + q).upper()


def group_quants(files: list[dict]) -> list[dict]:
    """GGUF files -> one entry per quant, multi-part splits (x-00001-of-00004.gguf) and quant folders merged."""
    groups: dict[str, dict] = {}
    for f in files:
        p = f["path"]
        if not p.lower().endswith(".gguf") or p.rsplit("/", 1)[-1].lower().startswith("mmproj"):
            continue
        key = SPLIT.sub("", p) if SPLIT.search(p) else p[:-5]
        g = groups.setdefault(key, dict(quant=quant_label(p), files=[], bytes=0))
        g["files"].append(p)
        g["bytes"] += _size(f)
    out = []
    for g in groups.values():
        g["files"].sort()
        g["size_gb"] = round(g["bytes"] / GB, 1)
        out.append(g)
    return sorted(out, key=lambda g: g["bytes"])


def repo_report(repo: str, hw: dict) -> dict:
    files = tree(repo)
    quants = group_quants(files)
    for q in quants:
        q["fits"] = fit(q["size_gb"], hw)
    st = [f for f in files if f["path"].endswith(".safetensors")]
    kind = "gguf" if quants else ("safetensors" if st else "other")
    note = None
    if kind == "safetensors":
        tot = sum(_size(f) for f in st) / GB
        note = (f"no GGUF here: {tot:.0f} GB of safetensors (FP8/BF16) for vLLM or SGLang on datacenter GPUs "
                f"(~{tot * 1.15:.0f} GB of GPU memory). Look for a GGUF repo of the same model: "
                f"`um llm search \"<model> GGUF\"`")
    return dict(repo=repo, kind=kind, quants=quants, note=note)


def pick(quants: list[dict], want: str | None = None) -> dict | None:
    if want:
        w = want.upper()
        exact = [q for q in quants if q["quant"] == w]
        part = [q for q in quants if w in q["quant"] or w in " ".join(q["files"]).upper()]
        return (exact or part or [None])[0]
    ok = [q for q in quants if q["fits"] in ("gpu", "ram+gpu", "ram")]
    return ok[-1] if ok else None  # quants are sorted by size: largest that fits


# --------------------------------------------------------------------------- download

def _models_root() -> Path:
    return Path(os.environ.get("UM_MODELS") or data_dir() / "models")


def download(repo: str, path: str, dest: Path, size: int, rev: str = "main"):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and (not size or dest.stat().st_size == size):
        print(f"  have {path}")
        return
    part = dest.with_name(dest.name + ".part")
    url = f"{HF}/{repo}/resolve/{rev}/{urllib.parse.quote(path)}"
    for attempt in range(8):
        have = part.stat().st_size if part.exists() else 0
        if size and have == size:
            break
        r = _req(url)
        if have:
            r.add_header("Range", f"bytes={have}-")
        try:
            with urllib.request.urlopen(r, timeout=120) as resp:
                if have and resp.status != 206:
                    have = 0  # server ignored the range: start over
                total = size or have + int(resp.headers.get("Content-Length") or 0)
                t0, done0 = time.time(), have
                with open(part, "ab" if have else "wb") as f:
                    while True:
                        chunk = resp.read(8 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        have += len(chunk)
                        rate = (have - done0) / max(time.time() - t0, 1e-3) / 2**20
                        pct = 100 * have / total if total else 0
                        print(f"\r  {path}: {have / GB:.1f}/{total / GB:.1f} GB {pct:5.1f}%  {rate:6.1f} MB/s ",
                              end="", file=sys.stderr, flush=True)
            print(file=sys.stderr)
            if not size or have >= size:
                break
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                die("gated repo: accept its terms on the model page and set HF_TOKEN")
            if e.code == 416:
                break
            print(f"\n  HTTP {e.code}, retrying", file=sys.stderr)
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            print(f"\n  {e}, resuming in {2 ** attempt}s", file=sys.stderr)
        time.sleep(min(2 ** attempt, 60))
    if size and part.stat().st_size != size:
        die(f"download of {path} incomplete after retries; run the same command again to resume")
    part.replace(dest)


def get(repo: str, quant: str | None, out_dir: str | None, yes: bool) -> Path:
    hw = hardware(Path(out_dir) if out_dir else None)
    rep = repo_report(repo, hw)
    if rep["kind"] != "gguf":
        die(rep["note"] or f"no GGUF files in {repo}")
    q = pick(rep["quants"], quant)
    if not q:
        if quant:
            die(f"no quant matching {quant}; have: {', '.join(x['quant'] for x in rep['quants'])}")
        small = rep["quants"][0]
        die(f"no quant fits this PC (budget {hw['budget_gb']} GB = RAM + VRAM - {HEADROOM_GB}); smallest is "
            f"{small['quant']} at {small['size_gb']} GB. Force one with --quant if you accept disk paging.")
    if q["fits"] in ("disk-paged", "no") and not yes:
        die(f"{q['quant']} is {q['size_gb']} GB but this PC's budget is {hw['budget_gb']} GB ({q['fits']}); "
            f"add --yes to download anyway")
    dest = Path(out_dir) if out_dir else _models_root() / repo.replace("/", "__") / q["quant"]
    need = q["bytes"] - sum((dest / Path(p).name).stat().st_size for p in q["files"] if (dest / Path(p).name).exists())
    free = shutil.disk_usage(dest if dest.exists() else _existing_parent(dest)).free
    if need > free:
        die(f"needs {need / GB:.1f} GB more disk, {free / GB:.1f} GB free at {dest}")
    print(f"{repo} {q['quant']}: {q['size_gb']} GB in {len(q['files'])} file(s) -> {dest}  (fits: {q['fits']})")
    sizes = {f["path"]: _size(f) for f in tree(repo)}
    for p in q["files"]:
        download(repo, p, dest / Path(p).name, sizes.get(p, 0))
    (dest / "um_model.json").write_text(json.dumps(dict(repo=repo, quant=q["quant"], files=[Path(p).name for p in q["files"]],
                                                        size_gb=q["size_gb"]), indent=1))
    print(f"done. next: um llm serve \"{dest}\"")
    return dest


def _existing_parent(p: Path) -> Path:
    while not p.exists() and p != p.parent:
        p = p.parent
    return p


# --------------------------------------------------------------------------- serve / chat

def first_gguf(target: str) -> Path:
    p = Path(target).expanduser()
    if p.is_file():
        return p
    if not p.is_dir():
        die(f"no such file or folder: {p}")
    ggufs = sorted(x for x in p.rglob("*.gguf") if not x.name.lower().startswith("mmproj"))
    if not ggufs:
        die(f"no .gguf in {p}")
    firsts = [x for x in ggufs if not SPLIT.search(x.name) or SPLIT.search(x.name).group(1) == "00001"]
    return firsts[0]


def model_bytes(gguf: Path) -> int:
    m = SPLIT.search(gguf.name)
    if not m:
        return gguf.stat().st_size
    stem = gguf.name[:m.start()]
    return sum(x.stat().st_size for x in gguf.parent.glob(f"{stem}-*-of-{m.group(2)}.gguf"))


def server_cmd(exe: str, gguf: Path, size_gb: float, hw: dict, ctx: int, port: int, host: str,
               extra: list[str] | None = None) -> list[str]:
    cmd = [exe, "-m", str(gguf), "-c", str(ctx), "--host", host, "--port", str(port), "--jinja"]
    if hw["vram_gb"] or is_mac():
        cmd += ["-ngl", "999"]
        if hw["vram_gb"] and size_gb + 2 > hw["vram_gb"]:
            # attention + shared weights on the GPU, the (huge, sparsely used) experts in RAM
            cmd += ["--cpu-moe"]
    return cmd + list(extra or [])


def _llama_server() -> str:
    exe = os.environ.get("UM_LLAMA_SERVER") or shutil.which("llama-server") or shutil.which("llama-server.exe")
    if not exe:
        die("llama-server not found. Get it from github.com/ggml-org/llama.cpp/releases "
            "(Windows + NVIDIA: llama-*-bin-win-cuda-*.zip plus the cudart zip; macOS: `brew install llama.cpp`), "
            "then put it on PATH or set UM_LLAMA_SERVER")
    return exe


def serve(target: str, ctx: int, port: int, host: str, dry: bool, extra: list[str]):
    gguf = first_gguf(target)
    hw = hardware(gguf.parent)
    size = model_bytes(gguf) / GB
    exe = "llama-server" if dry else _llama_server()
    cmd = server_cmd(exe, gguf, size, hw, ctx, port, host, extra)
    print(f"model {gguf.name} ({size:.1f} GB), fits: {fit(size, hw)}", file=sys.stderr)
    print(" ".join(f'"{c}"' if " " in c else c for c in cmd))
    if dry:
        return
    print(f"OpenAI-compatible API: http://{host}:{port}/v1  (web chat UI at http://{host}:{port}/)", file=sys.stderr)
    sys.exit(subprocess.call(cmd))


def chat(prompt: str, url: str, system: str | None, max_tokens: int):
    msgs = ([dict(role="system", content=system)] if system else []) + [dict(role="user", content=prompt)]
    body = json.dumps(dict(model="local", messages=msgs, max_tokens=max_tokens)).encode()
    r = urllib.request.Request(url.rstrip("/") + "/chat/completions", data=body,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=600) as resp:
            out = json.load(resp)
    except urllib.error.URLError as e:
        die(f"no server at {url} ({getattr(e, 'reason', e)}); start one with `um llm serve <model>`")
    print(out["choices"][0]["message"]["content"])


# --------------------------------------------------------------------------- cli

def _print_report(rep: dict, hw: dict):
    print(f"{rep['repo']}  ({rep['kind']})   this PC: {hw['ram_gb']} GB RAM + {hw['vram_gb']} GB VRAM "
          f"-> budget {hw['budget_gb']} GB, {hw['free_disk_gb']} GB free disk")
    if rep["note"]:
        print("  " + rep["note"])
    best = pick(rep["quants"])
    for q in rep["quants"]:
        mark = "  <- um llm get picks this" if q is best else ""
        print(f"  {q['quant']:<14} {q['size_gb']:>7.1f} GB  {len(q['files']):>2} file(s)  fits: {q['fits']:<10}{mark}")
    if rep["quants"] and not best:
        print(f"  nothing fits in {hw['budget_gb']} GB; disk-paged runs are seconds per token")


def main(a):
    if a.cmd == "hw":
        emit(hardware(Path(a.dir) if a.dir else None))
    elif a.cmd == "search":
        res = search(a.query, a.limit)
        if a.json:
            return emit(res, True)
        for m in res:
            print(f"{m['id']:<70} {m['downloads']:>9} dl  {'GGUF' if m['gguf'] else '    '}  {'gated' if m['gated'] else ''}")
        if not res:
            print("no matches; try fewer words, e.g. just the model name")
    elif a.cmd == "files":
        hw = hardware()
        rep = repo_report(a.repo, hw)
        emit(rep, True) if a.json else _print_report(rep, hw)
    elif a.cmd == "get":
        get(a.repo, a.quant, a.dir, a.yes)
    elif a.cmd == "serve":
        serve(a.model, a.ctx, a.port, a.host, a.dry_run, getattr(a, "passthrough", []))
    elif a.cmd == "chat":
        chat(a.prompt, a.url, a.system, a.max_tokens)


def register(sub):
    import argparse
    p = sub.add_parser("llm", help="run open-weight LLMs locally: search HF, size vs your PC, download GGUF, serve with llama.cpp",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cs = p.add_subparsers(dest="cmd", metavar="<cmd>")
    q = cs.add_parser("hw", help="RAM, VRAM, free disk and the model-size budget of this PC")
    q.add_argument("--dir", help="models folder to check free space on")
    q.set_defaults(func=main)
    q = cs.add_parser("search", help="search Hugging Face models")
    q.add_argument("query")
    q.add_argument("--limit", type=int, default=30)
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
    q = cs.add_parser("files", help="list a repo's GGUF quants with sizes and whether each fits this PC")
    q.add_argument("repo", help="owner/name")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
    q = cs.add_parser("get", help="download one quant (default: the largest that fits), resumable")
    q.add_argument("repo")
    q.add_argument("--quant", help="e.g. Q2_K, UD-Q2_K_XL, IQ1_M")
    q.add_argument("--dir", help="download folder (default ~/.universal-modder/models/<repo>/<quant>)")
    q.add_argument("--yes", action="store_true", help="download even if it won't fit in RAM + VRAM")
    q.set_defaults(func=main)
    q = cs.add_parser("serve", help="start llama-server on a downloaded model (OpenAI-compatible API); flags after -- go to llama-server")
    q.add_argument("model", help="model folder from `um llm get`, or a .gguf (first part of a split)")
    q.add_argument("--ctx", type=int, default=16384, help="context length (more = more memory)")
    q.add_argument("--port", type=int, default=8080)
    q.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to reach it from other devices on your LAN")
    q.add_argument("--dry-run", action="store_true", help="print the command only")
    q.set_defaults(func=main)
    q = cs.add_parser("chat", help="one-shot prompt to a running server")
    q.add_argument("prompt")
    q.add_argument("--url", default="http://127.0.0.1:8080/v1")
    q.add_argument("--system")
    q.add_argument("--max-tokens", type=int, default=1024)
    q.set_defaults(func=main)
