from __future__ import annotations

import uuid
import asyncio
from typing import Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import ensure_runtime_dirs
from .registry import get_model_for_task, public_registry
from .store import cancel_queued_job, create_job, delete_job, get_job, init_db, list_active_jobs, list_jobs, queue_position
from .worker import JobWorker


class JobCreate(BaseModel):
    model_id: str | None = None
    mode: Literal["generate", "edit"] = "generate"
    prompt: str = Field(min_length=1, max_length=4000)
    negative: str | None = None
    negative_prompt: str = ""
    width: int | None = Field(default=None, ge=256, le=1024)
    height: int | None = Field(default=None, ge=256, le=1024)
    steps: int | None = Field(default=None, ge=1, le=80)
    cfg: float | None = Field(default=None, ge=1, le=20)
    sampler: str | None = None
    scheduler: str | None = None
    seed: int = Field(default=1, ge=-1)
    init_image: str | None = None
    enhance_prompt: bool = False
    upscale: bool = False


app = FastAPI(title="VizGen Local Server")
worker = JobWorker()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1",
        "http://localhost",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    ensure_runtime_dirs()
    init_db()
    worker.start()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await worker.stop()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "ImageGen API", "status": "ok"}


@app.get("/api/models")
def models() -> list[dict]:
    return public_registry()


def public_job(job: dict) -> dict:
    outputs = job.get("outputs", [])
    output_url = outputs[0] if outputs else None
    status = "done" if job["status"] == "succeeded" else job["status"]
    return {
        **job,
        "job_id": job["id"],
        "status": status,
        "position": queue_position(job["id"]),
        "submitted_at": job["created_at"],
        "output_url": output_url,
    }


@app.post("/api/jobs", status_code=202)
def submit_job(payload: JobCreate) -> dict:
    mode = payload.mode
    if mode == "edit" and not payload.init_image:
        raise HTTPException(status_code=400, detail="edit jobs require init_image")

    try:
        model = get_model_for_task(mode, payload.model_id if mode == "generate" else None)
    except KeyError as exc:
        detail = "No enabled edit model is available" if mode == "edit" else "Unknown or disabled generation model"
        raise HTTPException(status_code=404, detail=detail) from exc

    payload_params = payload.model_dump(exclude={"model_id", "mode", "prompt", "negative", "negative_prompt"})
    params = dict(model.defaults)
    params.update({key: value for key, value in payload_params.items() if value is not None})
    job = create_job(
        job_id=str(uuid.uuid4()),
        model_id=model.id,
        mode=mode,
        prompt=payload.prompt,
        negative_prompt=payload.negative or payload.negative_prompt,
        params=params,
    )
    return public_job(job)


@app.get("/api/jobs")
def jobs(limit: int = 50) -> list[dict]:
    return [public_job(job) for job in list_jobs(limit=max(1, min(limit, 200)))]


@app.get("/api/queue")
def queue() -> list[dict]:
    return [public_job(job) for job in list_active_jobs()]


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    try:
        job = get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    return public_job(job)


@app.delete("/api/jobs/{job_id}")
def cancel_job(job_id: str) -> dict:
    try:
        return public_job(cancel_queued_job(job_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/gallery")
def gallery(page: int = 1, per_page: int = 24) -> dict:
    completed = [public_job(job) for job in list_jobs(limit=500) if job["status"] == "succeeded" and job["outputs"]]
    start = max(0, page - 1) * per_page
    end = start + max(1, min(per_page, 100))
    return {"items": completed[start:end], "total": len(completed), "page": page, "per_page": per_page}


@app.delete("/api/gallery/{job_id}")
def delete_gallery_item(job_id: str) -> dict[str, str]:
    try:
        delete_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    return {"status": "deleted"}


@app.websocket("/ws/jobs/{job_id}")
async def job_socket(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    last_payload: dict | None = None
    try:
        while True:
            job = public_job(get_job(job_id))
            if job != last_payload:
                if job["status"] == "done":
                    await websocket.send_json({"type": "done", "output_url": job["output_url"], "job_id": job_id})
                elif job["status"] in {"failed", "cancelled"}:
                    await websocket.send_json({"type": "error", "message": job.get("error") or job["status"], "job_id": job_id})
                else:
                    await websocket.send_json({
                        "type": "progress",
                        "job_id": job_id,
                        "progress": job.get("progress", 0),
                        "stage": job.get("stage", ""),
                        "stage_index": job.get("stage_index", 0),
                        "stage_total": job.get("stage_total", 1),
                        "message": job.get("message", ""),
                        "eta_seconds": job.get("eta_seconds", 0),
                        "step": 0,
                        "total_steps": job.get("params", {}).get("steps", 0),
                        "preview_url": None,
                    })
                last_payload = job
            if job["status"] in {"done", "failed", "cancelled"}:
                return
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return
    except KeyError:
        await websocket.close(code=1008)


@app.websocket("/api/ws/jobs/{job_id}")
async def legacy_job_socket(websocket: WebSocket, job_id: str) -> None:
    await job_socket(websocket, job_id)


@app.websocket("/ws/queue")
async def queue_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    last_payload: list[dict] | None = None
    try:
        while True:
            payload = [public_job(job) for job in list_active_jobs()]
            if payload != last_payload:
                await websocket.send_json(payload)
                last_payload = payload
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return


@app.websocket("/api/ws/queue")
async def legacy_queue_socket(websocket: WebSocket) -> None:
    await queue_socket(websocket)
