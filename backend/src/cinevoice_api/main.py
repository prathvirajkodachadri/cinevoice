from __future__ import annotations

import asyncio
import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint

from cinevoice import __version__ as engine_version
from cinevoice.ai import find_deepfilter

from .job_store import JobNotFoundError, JobStore
from .media import ACCEPTED_EXTENSIONS, available_extensions, ffmpeg_available
from .profiles import list_profiles
from .schemas import HealthResponse, JobPublic
from .settings import Settings
from .tasks import Processor

settings = Settings.from_environment()
store = JobStore(settings.data_dir, settings.retention_hours)
processor = Processor(settings, store)


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(15 * 60)
        await asyncio.to_thread(store.cleanup_expired)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await asyncio.to_thread(store.cleanup_expired)
    await asyncio.to_thread(store.recover_interrupted)
    cleanup_task = asyncio.create_task(_cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task


app = FastAPI(
    title="CineVoice Enhance API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


@app.middleware("http")
async def security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; "
        "object-src 'none'; script-src 'self' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https://fastapi.tiangolo.com; media-src 'self' blob:; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net"
    )
    api_path = request.url.path == "/api" or request.url.path.startswith("/api/")
    if api_path:
        response.headers["Cache-Control"] = "private, no-store"
    elif request.url.path.startswith("/assets/") and response.status_code < 400:
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


def _links(job_id: str) -> dict[str, str]:
    base = f"/api/v1/jobs/{job_id}"
    return {
        "self": base,
        "source": f"{base}/source",
        "result": f"{base}/result",
        "report": f"{base}/report",
    }


def _public_job(metadata: dict[str, object]) -> JobPublic:
    return JobPublic(**metadata, links=_links(str(metadata["id"])))


def _metadata(job_id: str) -> dict[str, object]:
    try:
        return store.get(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job not found or expired") from exc


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        version=f"web-0.1.0 / engine-{engine_version}",
        ai_denoise_available=find_deepfilter() is not None,
        ai_denoise_required=settings.require_ai,
        ffmpeg_available=ffmpeg_available(),
        accepted_extensions=sorted(available_extensions()),
        profiles=list_profiles(),
        limits={
            "max_upload_mb": settings.max_upload_bytes // (1024 * 1024),
            "max_duration_seconds": settings.max_duration_seconds,
            "retention_hours": settings.retention_hours,
        },
        privacy={
            "server_side_processing": True,
            "automatic_deletion": True,
            "retention_hours": settings.retention_hours,
        },
    )


@app.post("/api/v1/jobs", response_model=JobPublic, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    request: Request,
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(description="Audio file")],
    profile: Annotated[str, Form()] = "studio",
    remove_noise: Annotated[bool, Form()] = True,
) -> JobPublic:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            request_bytes = int(content_length)
        except ValueError:
            request_bytes = 0
        # Leave room for multipart headers while rejecting obviously oversized requests early.
        if request_bytes > settings.max_upload_bytes + 1024 * 1024:
            raise HTTPException(status_code=413, detail="Upload exceeds the size limit")

    valid_profiles = {item["id"] for item in list_profiles()}
    if profile not in valid_profiles:
        raise HTTPException(status_code=400, detail="Unknown enhancement profile")
    if remove_noise and find_deepfilter() is None:
        raise HTTPException(
            status_code=503,
            detail="AI background-noise removal is unavailable on this server",
        )
    if settings.require_ai and not remove_noise:
        raise HTTPException(status_code=400, detail="This server requires AI noise removal")

    filename = store.safe_filename(file.filename)
    extension = Path(filename).suffix.lower()
    if extension not in ACCEPTED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported audio format")
    if extension not in available_extensions():
        raise HTTPException(
            status_code=503,
            detail="This audio format requires FFmpeg, which is unavailable on the server",
        )

    await asyncio.to_thread(store.cleanup_expired)
    metadata = store.create(filename=filename, profile=profile, remove_noise=remove_noise)
    directory = store.directory(str(metadata["id"]))
    upload_path = directory / f"source{extension}"

    total = 0
    try:
        with upload_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="Upload exceeds the size limit")
                destination.write(chunk)
    except Exception:
        store.delete(str(metadata["id"]))
        raise
    finally:
        await file.close()

    if total == 0:
        store.delete(str(metadata["id"]))
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    metadata = store.update(
        str(metadata["id"]),
        progress=5,
        stage="Queued for processing",
        source_bytes=total,
    )
    background_tasks.add_task(processor.run, str(metadata["id"]), upload_path)
    return _public_job(metadata)


@app.get("/api/v1/jobs/{job_id}", response_model=JobPublic)
def get_job(job_id: str) -> JobPublic:
    return _public_job(_metadata(job_id))


@app.delete("/api/v1/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str) -> None:
    try:
        store.delete(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job not found or expired") from exc


def _job_file(job_id: str, filename: str, require_complete: bool = False) -> Path:
    metadata = _metadata(job_id)
    if require_complete and metadata["status"] != "completed":
        raise HTTPException(status_code=409, detail="Processing is not complete")
    path = store.directory(job_id) / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File is unavailable")
    return path


@app.get("/api/v1/jobs/{job_id}/source")
def source_audio(job_id: str, play: bool = False) -> FileResponse:
    metadata = _metadata(job_id)
    directory = store.directory(job_id)
    candidates = sorted(
        path
        for path in directory.glob("source.*")
        if path.suffix.lower() in ACCEPTED_EXTENSIONS
    )
    if not candidates:
        raise HTTPException(status_code=404, detail="Source is unavailable")
    path = candidates[0]
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    filename = None if play else str(metadata["original_filename"])
    return FileResponse(path, media_type=media_type, filename=filename)


@app.get("/api/v1/jobs/{job_id}/result")
def result_audio(job_id: str, play: bool = False) -> FileResponse:
    path = _job_file(job_id, "enhanced.wav", require_complete=True)
    filename = None if play else "cinevoice-enhanced.wav"
    return FileResponse(path, media_type="audio/wav", filename=filename)


@app.get("/api/v1/jobs/{job_id}/report")
def result_report(job_id: str) -> FileResponse:
    path = _job_file(job_id, "report.json", require_complete=True)
    return FileResponse(path, media_type="application/json", filename="cinevoice-report.json")


@app.exception_handler(413)
async def upload_too_large(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=413, content={"detail": exc.detail})


frontend = settings.frontend_dir
if frontend is not None and (frontend / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")


@app.api_route("/favicon.svg", methods=["GET", "HEAD"], include_in_schema=False)
def favicon() -> Response:
    if frontend is None or not (frontend / "favicon.svg").is_file():
        raise HTTPException(status_code=404, detail="Favicon not found")
    return FileResponse(
        frontend / "favicon.svg",
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
def legacy_favicon() -> RedirectResponse:
    return RedirectResponse(
        "/favicon.svg",
        status_code=status.HTTP_308_PERMANENT_REDIRECT,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
def frontend_route(path: str) -> Response:
    if path == "api" or path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found")
    if frontend is not None and path:
        public_file = (frontend / path).resolve()
        if frontend in public_file.parents and public_file.is_file():
            return FileResponse(
                public_file,
                media_type=mimetypes.guess_type(public_file.name)[0],
                headers={"Cache-Control": "public, max-age=86400"},
            )
    if Path(path).suffix:
        raise HTTPException(status_code=404, detail="Static file not found")
    if frontend is None or not (frontend / "index.html").is_file():
        return HTMLResponse(
            "<h1>CineVoice API is running</h1>"
            "<p>Build the frontend to enable the web interface.</p>"
        )
    return FileResponse(
        frontend / "index.html",
        media_type="text/html",
        headers={"Cache-Control": "no-cache"},
    )
