from __future__ import annotations

import asyncio
import json
import sys

from .comfy_client import ComfyUIClient
from .config import PROJECT_DIR
from .registry import get_model
from .store import next_queued_job, update_job, utc_now

ENHANCER = PROJECT_DIR / "scripts" / "prompt_enhance.py"


def _gen_eta(mode: str, params: dict) -> float:
    """Rough image/edit ETA (s). Cold text encoding can dominate on CPU."""
    steps = int(params.get("steps", 12))
    return 540 + steps * 6


class JobWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self.client = ComfyUIClient()

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task

    async def _run(self) -> None:
        while not self._stop.is_set():
            job = next_queued_job()
            if job is None:
                await asyncio.sleep(1)
                continue
            await self._run_job(job)

    async def _run_enhancer(self, prompt: str, mode: str) -> tuple[str, str]:
        """Run Qwen enhancer as a subprocess (CPU). Process exit releases the
        model. Returns (enhanced_prompt, negative_prompt); empty on failure."""
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(ENHANCER), prompt,
                "--mode", "image", "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(PROJECT_DIR),
            )
            out, _err = await asyncio.wait_for(proc.communicate(), timeout=300)
            data = json.loads(out.decode("utf-8", errors="replace").strip())
            return data.get("enhanced", ""), data.get("negative", "")
        except Exception:
            return "", ""

    async def _run_job(self, job: dict) -> None:
        job_id = job["id"]
        try:
            model = get_model(job["model_id"])
            params = job["params"]
            mode = job["mode"]

            want_enhance = bool(params.get("enhance_prompt"))
            want_upscale = bool(params.get("upscale")) and mode in {"generate", "edit"}

            plan: list[tuple[str, float]] = []
            if want_enhance:
                plan.append(("enhance", 120.0))  # cold Qwen CPU load
            plan.append(("generate", _gen_eta(mode, params)))
            if want_upscale:
                plan.append(("upscale", 300.0))  # tiled x4 on 1650 Ti

            total_eta = sum(e for _, e in plan) or 1.0
            done_eta = 0.0
            stage_total = len(plan)

            async def emit(stage_key: str, stage_idx: int, stage_prog: float, message: str) -> None:
                stage_eta = plan[stage_idx][1]
                elapsed_eta = done_eta + stage_eta * (stage_prog / 100.0)
                overall = (elapsed_eta / total_eta) * 100.0
                remaining = max(total_eta - elapsed_eta, 0.0)
                update_job(
                    job_id,
                    status="running",
                    stage=stage_key,
                    stage_index=stage_idx + 1,
                    stage_total=stage_total,
                    progress=round(min(overall, 99.0), 1),
                    eta_seconds=round(remaining, 0),
                    message=message,
                )

            update_job(
                job_id, status="running", started_at=utc_now(), progress=1,
                stage=plan[0][0], stage_index=1, stage_total=stage_total,
                eta_seconds=round(total_eta, 0), message="Starting pipeline",
            )

            cur_prompt = job["prompt"]
            cur_negative = job["negative_prompt"]
            gen_outputs: list[str] = []

            for idx, (stage_key, stage_eta) in enumerate(plan):
                if stage_key == "enhance":
                    await self.client.free()  # release resident gen model -> RAM for Qwen
                    await emit("enhance", idx, 5, "Loading prompt enhancer (Qwen, CPU)")
                    enhanced, negative = await self._run_enhancer(cur_prompt, mode)
                    if enhanced:
                        cur_prompt = enhanced
                    if negative:
                        cur_negative = negative
                    update_job(job_id, prompt=cur_prompt, negative_prompt=cur_negative)
                    await emit("enhance", idx, 100, "Prompt enhanced")

                elif stage_key == "generate":
                    await self.client.free()  # ensure Qwen released before gen model loads
                    await emit("generate", idx, 1, "Loading model")
                    job2 = {**job, "prompt": cur_prompt, "negative_prompt": cur_negative, "params": params}

                    async def on_prog(p: float, m: str, _idx: int = idx) -> None:
                        await emit("generate", _idx, p, m)

                    gen_outputs = await self.client.run_workflow(model, job2, on_progress=on_prog)

                elif stage_key == "upscale":
                    await self.client.free()  # release gen model -> VRAM for upscaler
                    await emit("upscale", idx, 1, "Loading upscaler (RealESRGAN)")

                    async def on_prog_u(p: float, m: str, _idx: int = idx) -> None:
                        await emit("upscale", _idx, p, m)

                    if gen_outputs:
                        upscaled = await self.client.run_upscale(gen_outputs[0], on_progress=on_prog_u)
                        if upscaled:
                            gen_outputs = upscaled

                done_eta += stage_eta

            await self.client.free()  # leave the GPU/RAM clean when idle
            update_job(
                job_id, status="succeeded", progress=100, stage="done",
                stage_index=stage_total, stage_total=stage_total, eta_seconds=0,
                message="Complete", outputs=gen_outputs, finished_at=utc_now(),
            )
        except Exception as exc:
            update_job(
                job_id, status="failed", progress=100, stage="failed",
                eta_seconds=0, message="Generation failed", error=str(exc),
                finished_at=utc_now(),
            )
