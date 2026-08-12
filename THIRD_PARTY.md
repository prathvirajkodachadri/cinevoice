# Third-party components

## DeepFilterNet

The default x86_64 Docker build downloads the standalone DeepFilterNet `deep-filter` v0.5.6 binary
from the upstream GitHub release and verifies this SHA-256 before installation:

```text
70775e251eee44c0f2451a1e833326cf8bcbbe304d3e7cd12851e6fce72ef7da
```

Upstream: https://github.com/Rikorose/DeepFilterNet

DeepFilterNet is not committed to this repository. Distributors must preserve its applicable MIT and
Apache-2.0 notices and separately confirm the terms for the included pretrained weights at the pinned
revision.

## Application dependencies

The backend uses FastAPI, Uvicorn, NumPy, SciPy, SoundFile/libsndfile and python-multipart. The frontend
uses React and Vite. The Docker runtime includes FFmpeg. Produce an SBOM and license bundle from the
exact release lock before public or commercial distribution.
