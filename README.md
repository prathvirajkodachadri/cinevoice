# CineVoice Web

A GitHub-ready, local-first web application where a user uploads audio, AI removes background noise,
a conservative mastering chain enhances the voice, and the user compares and downloads the result.

![Status](https://img.shields.io/badge/status-production%20foundation-76edab)

## User workflow

```text
Upload audio → choose Natural / Studio / Deep Narration
→ AI noise cleanup → voice enhancement → A/B preview → download WAV
```

Supported inputs: WAV, FLAC, OGG, MP3, M4A and AAC. The enhanced delivery file is WAV.

## Start the complete website

Install Docker Desktop, then run one command in this repository:

```bash
docker compose up --build
```

Open:

```text
http://localhost:8080
```

The x86_64 Docker image builds the React website, FastAPI backend, FFmpeg media layer, a checksum-
verified DeepFilterNet 0.5.6 runtime, and the deterministic audio engine. Other architectures build
without the optional AI binary and remain fully usable for deterministic enhancement. Uploaded jobs
are deleted after 24 hours by default.

## What version 0.1 does

- Drag-and-drop audio upload.
- DeepFilterNet speech denoising when enabled.
- 48 kHz preparation through native decoding or FFmpeg.
- High-pass filtering, conservative EQ, compression, subtle saturation and de-essing.
- Integrated-loudness targeting and true-peak limiting.
- Side-by-side original/enhanced playback with automatic A/B pause behavior.
- Upload and processing progress, clear failure recovery, and session restoration after refresh.
- Technical JSON report with before/after measurements and file hashes (no host paths).
- Non-destructive processing; the upload is never overwritten.
- Automatic expiry, immediate job deletion, upload/duration limits, and atomic metadata writes.
- Capability-aware format controls when FFmpeg or the optional AI model is unavailable.

## Profiles

- **Natural:** gentle cleanup, -16 LUFS target.
- **Studio:** balanced clarity and polish, -14 LUFS target.
- **Deep Narration:** controlled low mids and cinematic presence, -14 LUFS target.

The profiles are intentionally conservative. Version 0.1 does not change pitch or clone a voice.

## Development without Docker

Backend:

```bash
python -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
pip install -e "./backend[dev]"
CINEVOICE_FRONTEND_DIR= uvicorn cinevoice_api.main:app --reload
```

Frontend:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`; Vite proxies `/api` to port 8000.

Install DeepFilterNet separately when running outside Docker. If it is unavailable, the web UI clearly
disables AI noise removal while deterministic enhancement remains usable.

Run the complete quality suite:

```bash
python -m pip install -e "./backend[dev]"
ruff check backend/src backend/tests
pytest backend
cd frontend && npm ci && npm run build
```

## API

- `GET /api/health` — capabilities, limits and profiles.
- `POST /api/v1/jobs` — multipart upload and enhancement options.
- `GET /api/v1/jobs/{id}` — progress and result metadata.
- `GET /api/v1/jobs/{id}/source` — original recording for playback or download.
- `GET /api/v1/jobs/{id}/result` — enhanced WAV.
- `GET /api/v1/jobs/{id}/report` — technical report.
- `DELETE /api/v1/jobs/{id}` — immediate deletion.
- `GET /api/docs` — OpenAPI interface.

## Production deployment boundary

The included single-container deployment is suitable for private validation and a controlled pilot.
A public no-login service must additionally have:

- TLS and a reverse proxy/CDN.
- IP/user rate limiting and bot protection.
- Malware scanning and stronger media sandboxing.
- Object storage with lifecycle deletion.
- Redis-backed distributed jobs and isolated CPU/GPU workers.
- Observability without recording filenames or audio content.
- Signed privacy policy, terms, abuse handling and regional compliance review.
- A validated multilingual audio-quality corpus.

Do not advertise version 0.1 as certified or unlimited. See [`docs/PRODUCTION.md`](docs/PRODUCTION.md).

## Quality policy

AI is used for restoration, not for fabricating identity. Deterministic DSP handles tonal balance,
dynamics and delivery. Formant shifting is excluded until it passes transparent listening tests.
Metering and limiter behavior must be cross-validated against trusted BS.1770/true-peak references
before a public 1.0 release.

## License

Dual-licensed under MIT or Apache-2.0. DeepFilterNet and all model weights retain their upstream terms;
review and pin them before commercial distribution.
