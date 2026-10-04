"""Text/image -> 3D models from Mint (https://mint.gg): plain REST, no SDK. Needs MINT_API_KEY (env or a .env file).

    um mint model "a small ceramic lamp with an orange shade" --max-credits 10000
    um mint model "a friendly robot guide, full body" --rigging-pose t_pose --preset production
    um mint model --image concept.png                # one image (or 2-8 --image views of the same object) -> 3D
    um mint model "a treasure chest" --review        # stop at the Preview, then:
    um mint approve <operation-id>  |  um mint revise <operation-id> "make the lid rounder"
    um mint wait <operation-id>                      # resume polling a started job; downloads when it finishes
    um mint files <model-id> --formats glb,fbx       # (re)download a model's files
    um mint optimize <model-id>                      # lighter, game-ready GLB
    um mint convert <model-id> fbx                   # other formats (targetFormats)
    um mint estimate --preset production | um mint usage | um mint me
    um mint api POST /models/<id>:animate key=value key:=json    # any other route of the API

`model` starts a job, polls it (2 s, x1.6, capped at 15 s, 30 min max) and downloads every file of the result
(GLB, optimized GLB, FBX, OBJ, USDZ, STL, preview) into --out, appending a line to <out>/mint_manifest.jsonl.
Every POST carries an Idempotency-Key (pass --idempotency-key to pick it; reuse it only for the same request),
so a retried request never starts or bills a second job. --max-credits checks Mint's price estimate first and
refuses to start above the cap. Exact fields of every route: https://api.mint.gg/openapi.json
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from um.common import die

BASE = "https://api.mint.gg/v1"
DOCS = "https://docs.mint.gg/developers/quickstart"
# stop polling on these; billing_required waits for a human to top up, so it ends the wait too
TERMINAL = {"preview_ready", "billing_required", "succeeded", "partially_succeeded", "failed", "canceled"}
PRESETS = ["fast", "standard", "production"]
IMAGE_PROMPT = "Create a 3D model matching the uploaded reference image."
# model.assets fields -> file stem suffix (used when the artifact manifest has nothing)
ASSET_FIELDS = [("glbUrl", "", ".glb"), ("optimizedGlbUrl", "optimized", ".glb"), ("fbxUrl", "", ".fbx"),
                ("objUrl", "", ".obj"), ("usdzUrl", "", ".usdz"), ("stlUrl", "", ".stl"),
                ("previewImageUrl", "preview", ".png"), ("thumbnailUrl", "thumb", ".png")]
EXT = {"model/gltf-binary": ".glb", "model/gltf+json": ".gltf", "model/vnd.usdz+zip": ".usdz", "model/stl": ".stl",
       "model/obj": ".obj", "application/zip": ".zip", "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
       "video/mp4": ".mp4", "audio/mpeg": ".mp3", "audio/wav": ".wav"}
_ID = re.compile(r"^[A-Za-z0-9_-]+$")
_urlopen = urllib.request.urlopen     # swapped out by the tests
_sleep = time.sleep


def _headers(h) -> dict:
    return {str(k).lower(): v for k, v in (h.items() if h else [])}


class ApiError(Exception):
    def __init__(self, method, path, status, problem, headers):
        self.method, self.path, self.status, self.problem = method, path, status, problem or {}
        h = _headers(headers)
        self.request_id, self.retry_after = h.get("x-request-id"), h.get("retry-after")
        super().__init__(self.describe())

    @property
    def type(self) -> str:
        return str(self.problem.get("type") or "")

    def describe(self) -> str:
        p = self.problem
        lines = [f"mint {self.method} {self.path} -> HTTP {self.status}: {p.get('detail') or p.get('title') or 'request failed'}"]
        if self.type:
            lines.append(f"  type: {self.type}")
        for e in (p.get("errors") or [])[:5]:
            if isinstance(e, dict):
                lines.append(f"  - {e.get('path') or '(body)'}: {e.get('message')} [{e.get('code')}]")
        if self.status in (401, 403):
            lines.append("  check MINT_API_KEY (rotate it in Mint if it may have leaked)")
        elif self.status == 402:
            lines.append("  not enough Credits: `um mint usage`")
        elif self.status == 409 and "idempotency" in (self.type + str(p.get("detail") or "")).lower():
            lines.append("  that Idempotency-Key was already used for a different request; pick a new --idempotency-key")
        elif self.status == 404 and self.path.endswith(":generate"):
            lines.append("  unknown route; 3D models start at POST /v1/models:generate (`um mint model`)")
        if self.request_id:
            lines.append(f"  request id: {self.request_id} (quote it to Mint support)")
        return "\n".join(lines)


# --------------------------------------------------------------------------- auth + http


def mint_key() -> str:
    k = os.environ.get("MINT_API_KEY", "").strip()
    if not k and os.environ.get("MINT_API_KEY_FILE"):
        k = Path(os.environ["MINT_API_KEY_FILE"]).expanduser().read_text().strip()
    if not k:
        for env in (Path.cwd() / ".env", Path(__file__).resolve().parents[1] / ".env"):
            if env.exists():
                m = re.search(r"^\s*(?:export\s+)?MINT_API_KEY\s*=\s*['\"]?([^'\"\s]+)", env.read_text(), re.M)
                if m:
                    k = m.group(1)
                    break
    if not k:
        die(f"MINT_API_KEY is not set. Create an API key in Mint ({DOCS}) and `export MINT_API_KEY=...` "
            "(or put MINT_API_KEY=... in a .env file here)")
    return k


def base_url() -> str:
    b = (os.environ.get("MINT_API_BASE_URL") or BASE).strip().rstrip("/")
    u = urllib.parse.urlparse(b)
    if not u.hostname or not (u.scheme == "https" or (u.scheme == "http" and u.hostname in ("127.0.0.1", "localhost", "::1"))):
        die("MINT_API_BASE_URL must be an https URL (plain http only for a local mock on 127.0.0.1)")
    return b


def _origin(url: str) -> tuple:
    u = urllib.parse.urlparse(url)
    return u.scheme, u.hostname, u.port


def _retry_after(value) -> float | None:
    try:
        return max(0.0, min(float(value), 120.0))
    except (TypeError, ValueError):
        return None


def call(method: str, path: str, body=None, idem: str | None = None, timeout: float = 120) -> tuple[dict, dict]:
    """One API call -> (json body, headers). Reads, and POSTs that carry an Idempotency-Key, are retried on
    429/5xx/network errors (Retry-After respected); a POST without a key is retried only on 429, since a lost
    response could otherwise start a second paid job."""
    path = "/" + path.lstrip("/")
    if path.startswith("/v1/"):
        path = path[3:]
    url = base_url() + path
    h = {"Accept": "application/json", "User-Agent": "universal-modder"}
    key = mint_key()
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    if idem:
        h["Idempotency-Key"] = idem
    safe = method == "GET" or bool(idem)
    for attempt in range(5):
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        req.add_unredirected_header("Authorization", "Bearer " + key)   # urllib copies normal headers to redirects
        try:
            with _urlopen(req, timeout=timeout) as r:
                payload = r.read()
                headers = _headers(r.headers)
            try:
                return (json.loads(payload) if payload else {}), headers
            except ValueError:
                return {"detail": payload[:500].decode(errors="replace")}, headers
        except urllib.error.HTTPError as e:
            raw = e.read() or b""
            try:
                problem = json.loads(raw) if raw else {}
            except ValueError:
                problem = {"detail": raw[:500].decode(errors="replace")}
            err = ApiError(method, path, e.code, problem if isinstance(problem, dict) else {"detail": str(problem)}, e.headers)
            if attempt < 4 and (e.code == 429 or (safe and e.code in (500, 502, 503, 504))):
                wait = _retry_after(err.retry_after)
                _sleep(wait if wait is not None else 2 * (attempt + 1) + random.uniform(0, 1))
                continue
            raise err from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if safe and attempt < 4:
                _sleep(2 * (attempt + 1) + random.uniform(0, 1))
                continue
            reason = getattr(e, "reason", e)
            if not safe:
                die(f"mint {method} {path}: {reason}. The request may or may not have started a job; re-run with an "
                    "--idempotency-key to make retries safe, and check `um mint api GET /operations/<id>`")
            die(f"mint {method} {path}: {reason}")


def req(method: str, path: str, body=None, idem: str | None = None) -> dict:
    return call(method, path, body, idem)[0]


def _seg(value: str, what: str = "id") -> str:
    if not value or not _ID.match(value):
        die(f"not a valid Mint {what}: {value!r}")
    return value


def new_key(action: str) -> str:
    return f"um-{action}-{uuid.uuid4()}"


# --------------------------------------------------------------------------- inputs


def reference_url(ref: dict) -> str | None:
    assets = ref.get("assets") or {}
    return ref.get("url") or ref.get("sourceUrl") or ref.get("imageUrl") or assets.get("imageUrl") or assets.get("sourceUrl")


def upload_reference(src: str) -> str:
    """Local image or remote URL -> durable Mint reference-image URL (what imageUrl / sourceImages expect)."""
    if re.match(r"^https?://", src):
        body = {"sourceUrl": src}
    else:
        p = Path(src[1:] if src.startswith("@") else src)
        if not p.is_file():
            die(f"no such file: {p}")
        body = {"base64Data": base64.b64encode(p.read_bytes()).decode(), "fileName": p.name,
                "contentType": mimetypes.guess_type(p.name)[0] or "application/octet-stream"}
    ref = req("POST", "/reference-images", body, idem=new_key("reference"))
    url = reference_url(ref)
    if not url:
        die(f"Mint stored the reference image {ref.get('id')} but returned no URL for it")
    return url


def estimate(preset: str, review: bool) -> dict:
    return req("POST", "/pricing:estimate", {"operation": "model_generation", "generationPreset": preset,
                                             "generationMode": "review" if review else "auto"})


def check_budget(preset: str, review: bool, max_credits: float) -> dict:
    """Refuse to start a generation Mint estimates above max_credits, or one the account can't pay for."""
    est = estimate(preset, review).get("credits") or {}
    total = est.get("estimatedTotal") if est.get("estimatedTotal") is not None else est.get("requiredToStart")
    start = est.get("requiredToStart") if est.get("requiredToStart") is not None else total
    if not isinstance(total, (int, float)):
        die("Mint's price estimate had no Credits figure, so --max-credits can't be enforced; drop it to start anyway")
    print(f"  [mint] estimate: {total} Credits ({start} to start), cap {max_credits:g}", file=sys.stderr)
    if total > max_credits:
        die(f"Mint estimates {total} Credits for a {preset} model, above --max-credits {max_credits:g}; "
            "raise the cap or use --preset fast")
    avail = ((req("GET", "/usage").get("credits") or {}).get("totalAvailable"))
    if isinstance(avail, (int, float)) and isinstance(start, (int, float)) and avail < start:
        die(f"this Mint account has {avail} Credits available, {start} are needed to start; top up in Mint first")
    return est


# --------------------------------------------------------------------------- operations


def wait(op: dict, timeout: float = 1800) -> dict:
    """Poll an operation until it ends (or needs a person: preview_ready, billing_required)."""
    oid = _seg(op.get("id") or "", "operation id")
    t0, delay, last = time.time(), 2.0, None
    while True:
        status = op.get("status")
        if status != last:
            print(f"  [mint] {oid} {status}", file=sys.stderr)
            last = status
        if status in TERMINAL:
            return op
        if time.time() - t0 > timeout:
            die(f"operation {oid} still {status} after {timeout:.0f}s; resume with `um mint wait {oid}`")
        _sleep(delay + random.uniform(0, delay / 5))
        op, headers = call("GET", f"/operations/{oid}")
        hint = _retry_after(headers.get("retry-after"))
        delay = min(15.0, max(delay * 1.6, hint or 0))


def _billing(op: dict, idem: str | None) -> str:
    b = op.get("billing") or {}
    lines = [f"operation {op.get('id')} needs Credits ({b.get('reason') or 'billing_required'}): "
             f"{b.get('requiredCredits', '?')} required, {b.get('availableCredits', '?')} available"]
    if b.get("actionUrl"):
        lines.append(f"  top up: {b['actionUrl']}")
    if op.get("resource"):
        lines.append(f"  then: um mint resume {op.get('id')}")
    elif idem:
        lines.append(f"  then re-run the same command with --idempotency-key {idem}")
    return "\n".join(lines)


def _failure(op: dict) -> str:
    e = op.get("error") or {}
    msg = f"operation {op.get('id')} {op.get('status')}"
    if e:
        msg += f": {e.get('code')}" + (f" - {e.get('message')}" if e.get("message") else "")
    res = op.get("resource") or {}
    if op.get("status") == "failed" and res.get("type") == "model" and res.get("id"):
        msg += f"\n  retry it: um mint retry {res['id']}"
    return msg


# --------------------------------------------------------------------------- files


def _ext(url: str, mime: str = "", filename: str = "", default: str = "") -> str:
    for cand in (filename, urllib.parse.urlparse(url).path):
        m = re.search(r"(\.[A-Za-z0-9]{1,8})$", Path(cand).name) if cand else None
        if m:
            return m.group(1).lower()
    return EXT.get((mime or "").split(";")[0].strip().lower(), default)


def _clean(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s or "").strip("_")[:48]


def manifest_entries(man) -> list[dict]:
    """Downloadable files in an artifact manifest, whatever its nesting: [{url, filename, mime, label}]."""
    out, seen = [], set()

    def walk(o):
        if isinstance(o, dict):
            url = next((o[k] for k in ("downloadUrl", "url", "signedUrl", "href")
                        if isinstance(o.get(k), str) and re.match(r"^https?://", o[k])), None)
            looks_file = url and (any(k in o for k in ("filename", "fileName", "mimeType", "contentType", "sizeBytes", "format"))
                                  or re.search(r"\.[A-Za-z0-9]{1,8}$", urllib.parse.urlparse(url).path))
            if looks_file and url not in seen:
                seen.add(url)
                fn = next((o[k] for k in ("filename", "fileName", "name") if isinstance(o.get(k), str)), "")
                out.append(dict(url=url, filename=fn, mime=o.get("mimeType") or o.get("contentType") or "",
                                label=str(o.get("role") or o.get("kind") or o.get("variant") or "")))
            for k, v in o.items():
                if k not in ("runtime",):
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(man)
    return out


def asset_entries(assets: dict) -> list[dict]:
    return [dict(url=assets[k], filename="", mime="", label=label, default=ext)
            for k, label, ext in ASSET_FIELDS if isinstance(assets.get(k), str) and re.match(r"^https?://", assets[k])]


def plan_files(entries: list[dict], out: Path, name: str, formats: set[str] | None) -> list[tuple[str, Path]]:
    """Entries -> [(url, path)]: the first file of each type is <name>.<ext>, extras get a label suffix."""
    plan, used, first = [], set(), set()
    for e in entries:
        ext = _ext(e["url"], e.get("mime", ""), e.get("filename", ""), e.get("default", ""))
        label = _clean(e.get("label") or "")
        if not label and e.get("filename"):
            label = _clean(Path(e["filename"]).stem)
        if formats and "all" not in formats and not ({ext.lstrip(".")} | set(label.lower().split("_"))) & formats:
            continue
        if label.lower() in ("preview", "thumb", "thumbnail", "optimized") or ext in first:
            stem = f"{name}_{label or 'file'}"
        else:
            stem = name
            first.add(ext)
        path, n = out / f"{stem}{ext}", 1
        while path.name in used:
            n += 1
            path = out / f"{stem}_{n}{ext}"
        used.add(path.name)
        plan.append((e["url"], path))
    return plan


def fetch(url: str, path: Path):
    rq = urllib.request.Request(url, headers={"User-Agent": "universal-modder"})
    if _origin(url) == _origin(base_url()):
        rq.add_unredirected_header("Authorization", "Bearer " + mint_key())   # never to a CDN or a redirect target
    tmp = path.with_name(path.name + ".part")
    for attempt in range(3):
        try:
            with _urlopen(rq, timeout=600) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            tmp.replace(path)
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            code = getattr(e, "code", None)
            if attempt < 2 and (code is None or code in (429, 500, 502, 503, 504)):
                _sleep(2 * (attempt + 1))
                continue
            tmp.unlink(missing_ok=True)
            die(f"download of {path.name} failed: {getattr(e, 'reason', e)} (links expire: `um mint files` fetches fresh ones)")


def model_files(model_id: str, out: Path, name: str, formats: set[str] | None = None, asset_type: str = "model") -> list[str]:
    """Download a model's files: the artifact manifest first (Mint's documented route), model.assets otherwise."""
    _seg(model_id, "model id")
    entries = []
    try:
        entries = manifest_entries(req("GET", f"/assets/{_seg(asset_type, 'asset type')}/{model_id}/artifact-manifest"))
    except ApiError as e:
        if e.status not in (400, 404, 405, 422):
            raise
    if not entries:
        entries = asset_entries(req("GET", f"/models/{model_id}").get("assets") or {})
    if not entries:
        die(f"model {model_id} has no downloadable files yet (`um mint get {model_id}` shows its status)")
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for url, path in plan_files(entries, out, name, formats):
        fetch(url, path)
        print(path)
        files.append(str(path))
    if not files:
        die(f"none of model {model_id}'s files match --formats {','.join(sorted(formats or []))}")
    return files


def log(out: Path, rec: dict):
    out.mkdir(parents=True, exist_ok=True)
    rec = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), **{k: v for k, v in rec.items() if v not in (None, [], {})}}
    with open(out / "mint_manifest.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")


def finish(op: dict, out: Path, name: str, formats=None, idem=None, record=None, timeout=1800) -> dict:
    """Wait for an operation, then act on how it ended: download, show the Preview, or explain what's needed."""
    op = wait(op, timeout)
    status, res = op.get("status"), op.get("resource") or {}
    rec = dict(record or {}, operation=op.get("id"), status=status, resource=res or None, idempotency_key=idem,
               credits=op.get("credits"))
    if status in ("succeeded", "partially_succeeded"):
        if status == "partially_succeeded":
            print(f"  [mint] {op.get('id')} partially succeeded; keeping what finished", file=sys.stderr)
        if res.get("type") == "model" and res.get("id"):
            rec["files"] = model_files(res["id"], out, name, formats)
        else:
            print(json.dumps(op, indent=2))
        log(out, rec)
    elif status == "preview_ready":
        prev = (op.get("assets") or {}).get("previewImageUrl")
        if prev:
            out.mkdir(parents=True, exist_ok=True)
            path = out / f"{name}_preview{_ext(prev, default='.png')}"
            fetch(prev, path)
            print(path)
            rec["files"] = [str(path)]
        log(out, rec)
        print(f"  [mint] Preview ready. Look at it, then: um mint approve {op.get('id')}   or   "
              f"um mint revise {op.get('id')} \"<what to change>\"", file=sys.stderr)
    elif status == "billing_required":
        log(out, rec)
        die(_billing(op, idem))
    else:
        log(out, rec)
        die(_failure(op))
    return op


# --------------------------------------------------------------------------- commands


def _kv(pairs: list[str]) -> dict:
    """key=value (string) and key:=json (number/bool/list/object)."""
    out = {}
    for p in pairs or []:
        if ":=" in p:
            k, v = p.split(":=", 1)
            try:
                out[k] = json.loads(v)
            except ValueError:
                die(f"bad JSON in {p!r}")
        elif "=" in p:
            k, v = p.split("=", 1)
            out[k] = v
        else:
            die(f"bad argument {p!r}: use key=value or key:=json")
    return out


def _name(args, fallback: str) -> str:
    if getattr(args, "name", None):
        return args.name
    words = re.sub(r"[^a-z0-9 ]", "", (fallback or "").lower()).split()[:5]
    return "_".join(words) or "model"


def _formats(args) -> set[str] | None:
    f = getattr(args, "formats", None)
    return {x.strip().lower().lstrip(".") for x in f.split(",") if x.strip()} if f else None


def _started(op: dict, idem: str | None):
    if not isinstance(op, dict) or not op.get("id"):
        die(f"Mint returned no operation: {json.dumps(op)[:500]}")
    key = f" (Idempotency-Key {idem})" if idem else ""
    print(f"  [mint] started operation {op['id']}{key}; if this stops, resume with `um mint wait {op['id']}`", file=sys.stderr)


def cmd_model(args):
    images = args.image or []
    if len(images) > 8:
        die("Mint takes one --image, or 2-8 views of the same object")
    prompt = (args.prompt or "").strip() or (IMAGE_PROMPT if images else "")
    if not prompt:
        die("give a prompt, an --image, or both")
    idem = args.idempotency_key or new_key("model")
    if args.max_credits is not None:
        check_budget(args.preset, args.review, args.max_credits)
    body = {"prompt": prompt, "generationPreset": args.preset}
    if args.title:
        body["name"] = args.title
    if args.review:
        body["generationMode"] = "review"
    if args.rigging_pose:
        body["riggingPose"] = args.rigging_pose
    urls = [upload_reference(i) for i in images]
    if len(urls) == 1:
        body["imageUrl"] = urls[0]
    elif urls:
        body["sourceImages"] = urls
    body.update(_kv(args.set))
    op = req("POST", "/models:generate", body, idem=idem)
    _started(op, idem)
    if args.no_wait:
        print(json.dumps(op, indent=2))
        return
    record = dict(service="mint", route="models:generate", name=_name(args, prompt), input=body)
    finish(op, Path(args.out), _name(args, prompt), _formats(args), idem, record, args.timeout)


def cmd_action(args):
    """approve / revise / resume an operation, or retry / optimize / convert a model; then wait + download."""
    a = args.cmd
    idem = args.idempotency_key or new_key(a)
    if a in ("approve", "revise", "resume"):
        oid = _seg(args.operation_id, "operation id")
        body = {"feedback": args.feedback} if a == "revise" else {}
        path, name = f"/operations/{oid}:{a}", args.name or oid
    else:
        mid = _seg(args.model_id, "model id")
        body = {}
        if a == "optimize":
            body = {"optimizationLevel": args.level}
        elif a == "convert":
            body = {"targetFormats": args.target_formats}
            if args.title:
                body["name"] = args.title
        path, name = f"/models/{mid}:{a}", args.name or mid
    body.update(_kv(getattr(args, "set", None)))
    try:
        op = req("POST", path, body, idem=idem)
    except ApiError as e:
        # optimizing twice is a no-op on Mint's side: report it and hand over the files
        if a == "optimize" and e.status == 409 and e.type.endswith(("model-already-optimized", "model-optimization-in-progress")):
            print(f"  [mint] {e.type.split('/')[-1]}", file=sys.stderr)
            if e.type.endswith("model-already-optimized") and not args.no_wait:
                model_files(args.model_id, Path(args.out), name, _formats(args))
            return
        raise
    _started(op, idem)
    if args.no_wait:
        print(json.dumps(op, indent=2))
        return
    finish(op, Path(args.out), name, _formats(args), idem, dict(service="mint", route=path.lstrip("/"), input=body), args.timeout)


def cmd_wait(args):
    op = req("GET", f"/operations/{_seg(args.operation_id, 'operation id')}")
    finish(op, Path(args.out), args.name or args.operation_id, _formats(args), None,
           dict(service="mint", route="operations"), args.timeout)


def cmd_files(args):
    files = model_files(args.model_id, Path(args.out), args.name or args.model_id, _formats(args), args.asset_type)
    log(Path(args.out), dict(service="mint", route="files", resource={"type": args.asset_type, "id": args.model_id}, files=files))


def cmd_info(args):
    c = args.cmd
    if c == "me":
        r = req("GET", "/me")
    elif c == "usage":
        r = req("GET", "/usage")
    elif c == "estimate":
        r = estimate(args.preset, args.review)
    elif c == "op":
        r = req("GET", f"/operations/{_seg(args.operation_id, 'operation id')}")
    else:
        r = req("GET", f"/models/{_seg(args.model_id, 'model id')}")
    print(json.dumps(r, indent=2))


def cmd_api(args):
    method = args.method.upper()
    if method not in ("GET", "POST", "PATCH", "PUT", "DELETE"):
        die(f"unsupported method {args.method}")
    params, path = _kv(args.params), args.path
    body = None
    if method == "GET" and params:
        path += ("&" if "?" in path else "?") + urllib.parse.urlencode(params)
    elif method != "GET" and (params or method == "POST"):
        body = params
    r = req(method, path, body, idem=args.idempotency_key)
    if args.wait and isinstance(r, dict) and r.get("object") == "operation":
        finish(r, Path(args.out), args.name or r.get("id"), _formats(args), args.idempotency_key,
               dict(service="mint", route=path.lstrip("/"), input=body), args.timeout)
    else:
        print(json.dumps(r, indent=2))


def run(args):
    try:
        args.handler(args)
    except ApiError as e:
        die(e.describe())


def register(sub):
    import argparse
    p = sub.add_parser("mint", help="generate 3D models with Mint (text/image -> GLB/FBX/OBJ/USDZ)",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cs = p.add_subparsers(dest="cmd", metavar="<cmd>")

    def command(name, help_, handler, *positional, out=True, start=False, poll=False):
        q = cs.add_parser(name, help=help_)
        for pos in positional:
            q.add_argument(pos)
        if out:
            q.add_argument("--out", default="assets/gen", help="output folder (default assets/gen)")
            q.add_argument("--name", help="output file stem")
            q.add_argument("--formats", help="files to download, e.g. glb,fbx,preview (default: all)")
        if start:
            q.add_argument("--no-wait", action="store_true", help="start it, print the operation and exit")
            q.add_argument("--idempotency-key", help="stable key for this request; reuse it only to retry the same request")
        if start or poll:
            q.add_argument("--timeout", type=float, default=1800, help="seconds to keep polling (default 1800)")
        q.set_defaults(func=run, handler=handler)
        return q

    q = command("model", "text and/or image -> textured 3D model, downloaded", cmd_model, start=True)
    q.add_argument("prompt", nargs="?", help="what to make (optional with --image)")
    q.add_argument("--preset", default="standard", choices=PRESETS, help="fast (cheap iteration), standard, production")
    q.add_argument("--image", action="append", metavar="PATH|URL", help="reference image; 2-8 for views of one object")
    q.add_argument("--rigging-pose", choices=["t_pose", "a_pose"], help="full-body humanoid in a riggable pose (does not rig)")
    q.add_argument("--review", action="store_true", help="stop at the Preview for approve/revise")
    q.add_argument("--title", help="name shown in Mint")
    q.add_argument("--max-credits", type=float, help="refuse to start if Mint's estimate is above this")
    q.add_argument("--set", action="append", metavar="K=V", help="extra request field (repeatable; K:=json for numbers)")
    command("approve", "approve a Preview and finish the model", cmd_action, "operation_id", start=True)
    command("revise", "send Preview feedback; waits for the new Preview", cmd_action, "operation_id", "feedback", start=True)
    command("resume", "resume an operation after topping up Credits", cmd_action, "operation_id", start=True)
    command("retry", "retry a failed model", cmd_action, "model_id", start=True)
    q = command("optimize", "lighter, game-ready GLB of a model", cmd_action, "model_id", start=True)
    q.add_argument("--level", default="moderate", help="optimizationLevel (default moderate)")
    q = command("convert", "convert a model to other formats", cmd_action, "model_id", start=True)
    q.add_argument("target_formats", nargs="+", help="target formats, e.g. fbx obj usdz stl")
    q.add_argument("--title", help="name for the converted model")
    command("wait", "poll a started operation; download when it finishes", cmd_wait, "operation_id", poll=True)
    q = command("files", "download a model's files", cmd_files, "model_id")
    q.add_argument("--asset-type", default="model", help=argparse.SUPPRESS)
    command("get", "a model's status and file links", cmd_info, "model_id", out=False)
    command("op", "an operation's status", cmd_info, "operation_id", out=False)
    q = command("estimate", "Credits a model generation needs", cmd_info, out=False)
    q.add_argument("--preset", default="standard", choices=PRESETS)
    q.add_argument("--review", action="store_true")
    command("usage", "Credits available and used", cmd_info, out=False)
    command("me", "the account and key in use", cmd_info, out=False)
    q = command("api", "any route: um mint api POST /models/<id>:animate key=value key:=json", cmd_api, "method", "path", poll=True)
    q.add_argument("params", nargs="*", help="body fields (query for GET): key=value / key:=json")
    q.add_argument("--idempotency-key", help="makes a POST safe to retry")
    q.add_argument("--wait", action="store_true", help="if it returns an operation, poll it and download the result")
