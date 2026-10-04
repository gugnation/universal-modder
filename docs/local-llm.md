# Running GLM 5.3 (and other open-weight LLMs) locally

`um llm` takes a Hugging Face repo and gets it running on your own PC: it lists every GGUF quant against your
RAM and VRAM, downloads the one that fits (resumably), and starts llama.cpp's `llama-server`. That gives you an
OpenAI-compatible API at `http://127.0.0.1:8080/v1` plus a chat page at `http://127.0.0.1:8080/`. After the
download, nothing leaves your machine and nobody bills you per token.

## Which GLM 5.3 release can you actually run?

| Release | Format | Size on disk | Runs on |
|---|---|---|---|
| GLM 5.3 Uncensored FP8, full model (753B) | safetensors FP8 | ~750 GB | 8× H200/B200 server (vLLM/SGLang). **Not a PC.** |
| GLM 5.3 Flash Uncensored FP8 (320B / 18B active), dealignai or orcarouter (gated) | safetensors FP8 | ~320 GB | 4–8 datacenter GPUs (vLLM/SGLang). **Not a PC.** |
| GLM 5.3 Flash Abliterated GGUF (huihui-ai) | GGUF | pick a quant, see below | **PC with llama.cpp** |
| GLM 5.3 Flash Uncensored GGUF (AliceThirty, ungated) | GGUF | pick a quant, see below | **PC with llama.cpp** |

FP8 safetensors don't fit consumer hardware: FP8 means about 1 byte per parameter, all of it in GPU memory.
On a PC, use one of the two **GGUF Flash** repos.

How big a GGUF of the 320B Flash model is depends on the quant. These are rough figures, and `um llm files`
shows the exact ones:

| Quant | ≈ size | Needs RAM + VRAM of about | Quality |
|---|---|---|---|
| Q8_0 | ~340 GB | 384 GB+ | ≈ original |
| Q4_K_M | ~195 GB | 256 GB | very good |
| Q3_K_M / UD-Q3_K_XL | ~150 GB | 192 GB | good |
| Q2_K / UD-Q2_K_XL | ~115 GB | 128 GB | usable, noticeably dumber |
| IQ1_M / IQ1_S | ~70–75 GB | 96 GB | last resort |

The model is a mixture of experts: only 18B parameters are used per token. That makes "experts in system RAM,
everything else on the GPU" (llama.cpp `--cpu-moe`) workable, and `um llm serve` turns it on automatically
when the model is bigger than your VRAM. With DDR5, expect a few to ~15 tokens/s. A desktop with **128 GB RAM
plus any 12–24 GB NVIDIA card** runs a Q2-class quant, and 192–256 GB runs Q3/Q4. With 32–64 GB RAM, GLM 5.3
Flash won't run at a usable speed (llama.cpp would page weights from disk, at seconds per token). Pick a
smaller model in that case. `um llm` works the same for any GGUF repo.

## Setup on Windows (NVIDIA)

1. **llama.cpp**: from <https://github.com/ggml-org/llama.cpp/releases>, download
   `llama-<ver>-bin-win-cuda-12.4-x64.zip` and the matching `cudart-llama-bin-win-cuda-12.4-x64.zip`. Unzip
   both into the same folder (e.g. `C:\llama.cpp`). Then either add that folder to PATH or run
   `setx UM_LLAMA_SERVER C:\llama.cpp\llama-server.exe`.
   No NVIDIA GPU: use the `-cpu-x64` zip. AMD: use the `-vulkan-` zip.
2. **Python 3.10+** (`winget install Python.Python.3.12`). `um llm` uses only the standard library.
3. From the universal-modder folder, in PowerShell (WSL caps RAM, so run this natively on Windows):

```powershell
python -m um llm hw                                  # your RAM / VRAM / disk and the size budget
python -m um llm search "GLM-5.3 Flash GGUF"         # find the exact repo ids (huihui-ai/..., AliceThirty/...)
python -m um llm files huihui-ai/<repo-id-from-search>   # each quant, its size, fits: gpu / ram+gpu / disk-paged / no
python -m um llm get   huihui-ai/<repo-id-from-search>   # downloads the largest quant that fits; Ctrl+C and re-run resumes
python -m um llm serve "$HOME\.universal-modder\models\huihui-ai__<repo>\<QUANT>"
python -m um llm chat "Say hi in five words."        # in a second window, to check it answers
```

On Linux, macOS or WSL, `um llm ...` works as-is through `bin/um`.

Useful flags:
- `get --quant UD-Q2_K_XL` picks a specific quant. `get --dir D:\models\glm` puts it on a bigger drive (the
  tool checks free space first). Set `UM_MODELS=D:\models` to make that drive the default.
- `serve --ctx 32768` raises the context length (costs more memory). `serve --host 0.0.0.0` makes it
  reachable from your phone or another PC on the LAN. Anything after `--` goes straight to llama-server, e.g.
  `serve <dir> -- -t 16 --n-cpu-moe 30` (keep only the first 30 layers' experts on the CPU when you have
  spare VRAM).
- `serve --dry-run` only prints the llama-server command.
- Gated repos (orcarouter): accept the terms on the model page and create a read token at
  huggingface.co/settings/tokens. Then `setx HF_TOKEN hf_...` (Windows) or `export HF_TOKEN=...`.

## Using it from other apps

Anything that takes an OpenAI-compatible base URL works: base URL `http://127.0.0.1:8080/v1`, any API key
(e.g. `local`), any model name. That includes Open WebUI, SillyTavern, LM Studio's client side, Continue,
Aider and opencode, plus your own scripts (`openai` Python package with `base_url=`). For mods, a game-side
script can call the same endpoint for offline NPC dialogue.

## Troubleshooting

- `unknown model architecture` means your llama.cpp is older than the model, so get the latest release.
  GLM 5.x GGUFs need a build from 2026 (they use the `glm-dsa` / `glm5-next` architectures).
- Out of memory at load: lower `--ctx`, or move more experts to the CPU (`-- --n-cpu-moe 99`). If it still
  fails, pick a smaller quant.
- Slow (under 1 token/s): the model is bigger than RAM + VRAM and is being paged from disk. `um llm files`
  shows `fits: disk-paged` for these. Use a smaller quant.
- `um llm` reports a 401/403: the repo is gated. Accept its terms on the website and set `HF_TOKEN`. If
  huggingface.co is blocked where you are, set `HF_ENDPOINT` to a mirror.

## Caveats

- These uncensored/abliterated builds are community uploads, not official Z.ai releases. Before trusting a
  repo, check the uploader, the download count and the model card. GGUF and safetensors are data formats
  (`um llm` never loads pickled `.bin`/`.pt` files), but a bad quant can still produce garbage. Abliteration
  also usually costs a little quality compared with the base model.
- "MIT" covers the weights' license. You're still responsible for what you generate and publish with them.
- Free here means free to run. The official Z.ai API and OpenRouter's GLM 5.3 endpoints are paid.
