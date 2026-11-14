"""
ACE-Step 1.5 API server on Modal, for trill's backend to render against.

  python -m modal run infra/modal_acestep.py::download   # once: pull weights into the volume
  python -m modal deploy infra/modal_acestep.py          # prints the URL to use as ACESTEP_API_URL

The server keeps its task queue in memory, so exactly one container runs at a time;
/release_task and the /query_result polls that follow must land on the same process.
It scales to zero after SCALEDOWN seconds without a request.
"""
import subprocess

import modal

ACESTEP_REPO = "https://github.com/ace-step/ACE-Step-1.5.git"
ACESTEP_COMMIT = "ca1e85f"  # 2026-08-29, includes the 1.5 XL (4B DiT) models; trill's client is verified against it
ROOT = "/opt/acestep"
PORT = 8001
# 24 GB cards: enough for both DiT models plus the small LM without offloading.
# A10G is the fallback when Modal has no L4 free (seen 2026-11-14: "waiting to be scheduled on a GPU_L4 worker").
GPU = ["L4", "A10G"]
MODELS = ["acestep-v15-turbo", "acestep-v15-xl-turbo"]
SCALEDOWN = 300

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "ffmpeg", "libsndfile1", "build-essential")
    .pip_install("uv")
    .run_commands(
        f"git clone {ACESTEP_REPO} {ROOT}",
        f"cd {ROOT} && git checkout {ACESTEP_COMMIT}",
        f"cd {ROOT} && uv sync --frozen --no-dev --python 3.11",
    )
    .env({
        "ACESTEP_PROJECT_ROOT": ROOT,
        # Slot 1 is the free-tier model, slot 2 the paid one; requests pick with the "model" field.
        "ACESTEP_CONFIG_PATH": MODELS[0],
        "ACESTEP_CONFIG_PATH2": MODELS[1],
        "ACESTEP_INIT_LLM": "true",
        "ACESTEP_LM_MODEL_PATH": "acestep-5Hz-lm-0.6B",
        "ACESTEP_DOWNLOAD_SOURCE": "huggingface",
        "HF_HUB_ENABLE_HF_TRANSFER": "0",
        "TOKENIZERS_PARALLELISM": "false",
    })
    .workdir(ROOT)
)

app = modal.App("trill-acestep", image=image)
checkpoints = modal.Volume.from_name("trill-acestep-checkpoints", create_if_missing=True)
PY = f"{ROOT}/.venv/bin/python"


@app.function(volumes={f"{ROOT}/checkpoints": checkpoints}, timeout=3600)
def download():
    """Pull the main bundle (turbo DiT, VAE, text encoder), the small LM and the extra DiT models into the volume."""
    subprocess.run([PY, "-m", "acestep.model_downloader"], check=True, cwd=ROOT)
    for name in ["acestep-5Hz-lm-0.6B", *MODELS[1:]]:
        subprocess.run([PY, "-m", "acestep.model_downloader", "--model", name], check=True, cwd=ROOT)
    checkpoints.commit()


@app.function(
    gpu=GPU,
    volumes={f"{ROOT}/checkpoints": checkpoints},
    secrets=[modal.Secret.from_name("trill-acestep")],  # ACESTEP_API_KEY
    max_containers=1,
    scaledown_window=SCALEDOWN,
    timeout=3600,
)
@modal.concurrent(max_inputs=64)
@modal.web_server(PORT, startup_timeout=900)
def api():
    subprocess.Popen([PY, "-m", "acestep.api_server", "--host", "0.0.0.0", "--port", str(PORT)], cwd=ROOT)
