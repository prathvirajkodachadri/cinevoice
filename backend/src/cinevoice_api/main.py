from __future__ import annotations

import asyncio
import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from cinevoice import __version__ as engine_version
from cinevoice.ai import find_deepfilter

from .job_store import JobNotFoundError, JobStore
from .media import ACCEPTED_EXTENSIONS, ffmpeg_available
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
        ffmpeg_available=ffmpeg_available(),
        accepted_extensions=sorted(ACCEPTED_EXTENSIONS),
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
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(description="Audio file")],
    profile: Annotated[str, Form()] = "studio",
    remove_noise: Annotated[bool, Form()] = True,
) -> JobPublic:
    valid_profiles = {item["id"] for item in list_profiles()}
    if profile not in valid_profiles:
        raise HTTPException(status_code=400, detail="Unknown enhancement profile")

    filename = store.safe_filename(file.filename)
    extension = Path(filename).suffix.lower()
    if extension not in ACCEPTED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported audio format")

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
def source_audio(job_id: str) -> FileResponse:
    metadata = _metadata(job_id)
    directory = store.directory(job_id)
    candidates = list(directory.glob("source.*"))
    if not candidates:
        raise HTTPException(status_code=404, detail="Source is unavailable")
    path = candidates[0]
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=str(metadata["original_filename"]))


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


@app.get("/{path:path}", include_in_schema=False)
def frontend_route(path: str) -> HTMLResponse:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found")
    if frontend is None or not (frontend / "index.html").is_file():
        return HTMLResponse(
            "<h1>CineVoice API is running</h1>"
            "<p>Build the frontend to enable the web interface.</p>"
        )
    return HTMLResponse((frontend / "index.html").read_text(encoding="utf-8"))
