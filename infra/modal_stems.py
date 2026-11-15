"""
Stem separation for trill on Modal: splits a finished track into vocals, drums, bass and other.

  python -m modal deploy infra/modal_stems.py     # prints the URL to use as STEMS_API_URL

Uses Demucs (htdemucs) rather than ACE-Step's generative "extract" task: Demucs separates the
audio that is actually in the mix, so the four stems sum back to the original track, which is
what a DAW session needs. It runs in its own small container that only starts when someone
asks for stems, and scales to zero afterwards.

POST /separate   multipart: file=<audio>, name=<base filename>   Authorization: Bearer <ACESTEP_API_KEY>
  -> application/zip containing <name>_vocals.wav, _drums.wav, _bass.wav, _other.wav (44.1 kHz, 16-bit)
"""
import modal

MODEL = "htdemucs"
STEMS = ("vocals", "drums", "bass", "other")


def _fetch_weights():
    from demucs.pretrained import get_model

    get_model(MODEL)


image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "torch==2.4.1",
        "torchaudio==2.4.1",
        "demucs==4.0.1",
        "soundfile==0.12.1",
        "fastapi[standard]==0.115.5",
        "python-multipart==0.0.17",
    )
    .run_function(_fetch_weights)  # bake the weights into the image so a cold start does not download them
)

app = modal.App("trill-stems", image=image)


@app.function(
    gpu="T4",
    secrets=[modal.Secret.from_name("trill-acestep")],  # same ACESTEP_API_KEY the backend already holds
    max_containers=2,
    scaledown_window=120,
    timeout=900,
)
@modal.concurrent(max_inputs=1)
@modal.asgi_app()
def api():
    import io
    import os
    import re
    import subprocess
    import sys
    import tempfile
    import zipfile

    from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
    from fastapi.responses import Response

    web = FastAPI()

    @web.get("/health")
    def health():
        return {"ok": True, "model": MODEL, "stems": list(STEMS)}

    @web.post("/separate")
    async def separate(file: UploadFile = File(...), name: str = Form("track"), authorization: str = Header(None)):
        key = os.environ.get("ACESTEP_API_KEY", "")
        if not key or authorization != f"Bearer {key}":
            raise HTTPException(status_code=401, detail="unauthorized")
        base = re.sub(r"[^A-Za-z0-9._ -]", "", name).strip()[:80] or "track"
        ext = os.path.splitext(file.filename or "")[1].lower() or ".mp3"
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, f"input{ext}")
            with open(src, "wb") as fp:
                fp.write(await file.read())
            run = subprocess.run(
                [sys.executable, "-m", "demucs.separate", "-n", MODEL, "-d", "cuda", "-o", tmp, src],
                capture_output=True, text=True,
            )
            out = os.path.join(tmp, MODEL, "input")
            if run.returncode != 0 or not os.path.isdir(out):
                raise HTTPException(status_code=500, detail=(run.stderr or "separation failed")[-400:])
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:  # WAV barely compresses; stay fast
                for stem in STEMS:
                    z.write(os.path.join(out, f"{stem}.wav"), f"{base}_{stem}.wav")
            return Response(content=buf.getvalue(), media_type="application/zip")

    return web
