from __future__ import annotations

import copy
import asyncio
import base64
import json
import mimetypes
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import httpx
import websockets

from .config import COMFYUI_URL, PROJECT_DIR, WORKFLOWS_DIR
from .registry import ModelConfig

UPSCALE_SCRIPT = PROJECT_DIR / "scripts" / "upscale_image.py"
COMFY_OUTPUT_DIR = PROJECT_DIR / "engine" / "comfyui" / "output"


class ComfyUIError(RuntimeError):
    pass


def _replace_tokens(value: Any, tokens: dict[str, Any]) -> Any:
    if isinstance(value, str):
        if value.startswith("${") and value.endswith("}"):
            token_name = value[2:-1]
            if token_name in tokens:
                return tokens[token_name]
        for key, replacement in tokens.items():
            value = value.replace("${" + key + "}", str(replacement))
        return value
    if isinstance(value, list):
        return [_replace_tokens(item, tokens) for item in value]
    if isinstance(value, dict):
        return {key: _replace_tokens(item, tokens) for key, item in value.items()}
    return value


class ComfyUIClient:
    def __init__(self, base_url: str = COMFYUI_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = str(uuid.uuid4())

    def _build_prompt(self, model: ModelConfig, job: dict[str, Any]) -> dict[str, Any]:
        workflow_name = model.workflow
        workflow_path = WORKFLOWS_DIR / workflow_name
        if not workflow_path.exists():
            raise ComfyUIError(f"Workflow file not found: {workflow_path}")

        workflow_doc = json.loads(workflow_path.read_text(encoding="utf-8"))
        workflow = workflow_doc.get("prompt", workflow_doc)
        params = job["params"]
        tokens = {
            "prompt": job["prompt"],
            "negative_prompt": job["negative_prompt"],
            "seed": params.get("seed", 1),
            "width": params.get("width", 512),
            "height": params.get("height", 512),
            "steps": params.get("steps", 20),
            "cfg": params.get("cfg", 7),
            "sampler": params.get("sampler", "euler"),
            "scheduler": params.get("scheduler", "normal"),
            "mode": job["mode"],
            "init_image": params.get("init_image", ""),
        }
        prompt = _replace_tokens(copy.deepcopy(workflow), tokens)
        return prompt

    async def queue_workflow(self, model: ModelConfig, job: dict[str, Any], prompt_id: str | None = None) -> str:
        prompt = self._build_prompt(model, job)
        if job["mode"] == "edit" and job["params"].get("init_image"):
            image_name = await self._upload_init_image(job["params"]["init_image"])
            self._attach_init_image(prompt, image_name)
        self._patch_common_inputs(prompt, model, job, job["params"])

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/prompt",
                json={"prompt": prompt, "client_id": self.client_id, **({"prompt_id": prompt_id} if prompt_id else {})},
            )
            if response.status_code >= 400:
                raise ComfyUIError(response.text)
            data = response.json()
        return str(data["prompt_id"])

    async def _upload_init_image(self, init_image: str) -> str:
        header = ""
        payload = init_image
        if "," in init_image and init_image.startswith("data:"):
            header, payload = init_image.split(",", 1)

        content_type = "image/png"
        if header.startswith("data:"):
            content_type = header.removeprefix("data:").split(";")[0] or content_type
        suffix = mimetypes.guess_extension(content_type) or ".png"
        filename = f"imagegen_edit_{uuid.uuid4().hex}{suffix}"
        image_bytes = base64.b64decode(payload)

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/upload/image",
                data={"type": "input", "overwrite": "true"},
                files={"image": (filename, image_bytes, content_type)},
            )
            if response.status_code >= 400:
                raise ComfyUIError(response.text)
            data = response.json()

        name = data.get("name", filename)
        subfolder = data.get("subfolder", "")
        return f"{subfolder}/{name}" if subfolder else name

    def _attach_init_image(self, prompt: dict[str, Any], image_name: str) -> None:
        load_image_id: str | None = None
        numeric_ids = [int(node_id) for node_id in prompt if str(node_id).isdigit()]
        for node in prompt.values():
            if node.get("class_type") == "LoadImage":
                node.setdefault("inputs", {})["image"] = image_name
                return

        load_image_id = str(max(numeric_ids, default=0) + 1)
        prompt[load_image_id] = {
            "class_type": "LoadImage",
            "inputs": {"image": image_name},
        }

    async def free(self, unload_models: bool = True, free_memory: bool = True) -> None:
        """Release resident models + free VRAM/RAM between pipeline stages.

        This is the core of the load-only-when-needed / release-when-done policy:
        on a 4GB GPU / 16GB RAM box we must not hold the enhancer + image model
        + upscaler at once. Best-effort — never fatal if ComfyUI has no models loaded yet.
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                await client.post(
                    f"{self.base_url}/free",
                    json={"unload_models": unload_models, "free_memory": free_memory},
                )
        except Exception:
            pass

    async def _await_prompt(self, websocket, prompt_id: str, on_progress, phase: str) -> None:
        """Stream ComfyUI progress for one queued prompt, mapping to 0..100 of
        the current stage. `phase` is the human label (e.g. 'Inferencing')."""
        while True:
            raw_message = await asyncio.wait_for(websocket.recv(), timeout=7200)
            if not isinstance(raw_message, str):
                continue
            message = json.loads(raw_message)
            data = message.get("data", {})
            if data.get("prompt_id") not in {None, prompt_id}:
                continue
            if message.get("type") == "progress":
                value = float(data.get("value", 0))
                maximum = max(float(data.get("max", 1)), 1)
                percent = int((value / maximum) * 100)
                if on_progress:
                    await on_progress(min(percent, 99), f"{phase} — step {int(value)}/{int(maximum)}")
            if message.get("type") == "executing" and data.get("node") is None and data.get("prompt_id") == prompt_id:
                break

    async def run_workflow(self, model: ModelConfig, job: dict[str, Any], on_progress=None) -> list[str]:
        prompt_id = str(uuid.uuid4())
        ws_url = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        async with websockets.connect(f"{ws_url}/ws?clientId={self.client_id}", max_size=None) as websocket:
            prompt_id = await self.queue_workflow(model, job, prompt_id=prompt_id)
            if on_progress:
                await on_progress(2, "Loading model + encoding prompt")
            await self._await_prompt(websocket, prompt_id, on_progress, "Inferencing")
        return await self.wait_for_outputs(prompt_id)

    async def run_upscale(self, image_url: str, on_progress=None) -> list[str]:
        """RealESRGAN x4 via standalone script (avoids ComfyUI lowvram device bug).

        Fetch the generated image (usually a ComfyUI /view URL), upscale with
        scripts/upscale_image.py, drop the result into ComfyUI's output folder so
        gallery can keep using /view URLs.
        """
        if not UPSCALE_SCRIPT.exists():
            raise ComfyUIError(f"Upscale script missing: {UPSCALE_SCRIPT}")

        if on_progress:
            await on_progress(5, "Fetching image for upscale")
        async with httpx.AsyncClient(timeout=120) as client:
            img = await client.get(image_url)
            if img.status_code >= 400:
                raise ComfyUIError(f"Could not fetch image to upscale: {img.status_code}")

        COMFY_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stem = f"upscale_x4_{uuid.uuid4().hex}"
        with tempfile.TemporaryDirectory(prefix="imagegen_up_") as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / f"{stem}_src.png"
            dst = tmp_path / f"{stem}.png"
            src.write_bytes(img.content)

            if on_progress:
                await on_progress(15, "Running RealESRGAN x4")
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(UPSCALE_SCRIPT),
                str(src),
                "-o",
                str(dst),
                "--device",
                "auto",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(PROJECT_DIR),
            )
            _out, err = await asyncio.wait_for(proc.communicate(), timeout=900)
            if proc.returncode != 0 or not dst.exists():
                detail = err.decode("utf-8", errors="replace")[-800:]
                raise ComfyUIError(f"Upscale failed (code {proc.returncode}): {detail}")

            final_name = f"{stem}.png"
            final_path = COMFY_OUTPUT_DIR / final_name
            final_path.write_bytes(dst.read_bytes())

        if on_progress:
            await on_progress(100, "Upscale complete")
        return [
            f"{self.base_url}/view?filename={final_name}&subfolder=&type=output"
        ]

    async def _upload_bytes(self, image_bytes: bytes, ext: str = "png") -> str:
        filename = f"imagegen_up_{uuid.uuid4().hex}.{ext}"
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/upload/image",
                data={"type": "input", "overwrite": "true"},
                files={"image": (filename, image_bytes, f"image/{ext}")},
            )
            if response.status_code >= 400:
                raise ComfyUIError(response.text)
            data = response.json()
        name = data.get("name", filename)
        subfolder = data.get("subfolder", "")
        return f"{subfolder}/{name}" if subfolder else name

    async def wait_for_outputs(self, prompt_id: str) -> list[str]:
        async with httpx.AsyncClient(timeout=10) as client:
            for _ in range(7200):
                response = await client.get(f"{self.base_url}/history/{prompt_id}")
                if response.status_code >= 400:
                    raise ComfyUIError(response.text)
                history = response.json()
                if prompt_id in history:
                    return self._extract_outputs(history[prompt_id])
                await asyncio.sleep(1)
        raise ComfyUIError("Timed out waiting for ComfyUI output")

    def _patch_common_inputs(
        self,
        prompt: dict[str, Any],
        model: ModelConfig,
        job: dict[str, Any],
        params: dict[str, Any],
    ) -> None:
        paths = model.paths
        text_nodes = [
            node for _, node in sorted(prompt.items(), key=lambda item: int(item[0]) if item[0].isdigit() else 9999)
            if node.get("class_type") == "CLIPTextEncode"
        ]
        if text_nodes:
            text_nodes[0].setdefault("inputs", {})["text"] = job["prompt"]
        if len(text_nodes) > 1:
            text_nodes[1].setdefault("inputs", {})["text"] = job["negative_prompt"]

        steps = int(params.get("steps", 12))
        seed = int(params.get("seed", 1))
        if seed < 0:
            seed = uuid.uuid4().int % (2**63)
        for node in prompt.values():
            inputs = node.setdefault("inputs", {})
            class_type = node.get("class_type", "")
            if class_type == "UnetLoaderGGUF" and paths.get("unet"):
                inputs["unet_name"] = Path(paths["unet"]).name
            if class_type == "CLIPLoader" and paths.get("text_encoder"):
                inputs["clip_name"] = Path(paths["text_encoder"]).name
            if class_type == "VAELoader" and paths.get("vae"):
                inputs["vae_name"] = Path(paths["vae"]).name
            if class_type == "EmptyLatentImage":
                inputs["width"] = int(params.get("width", inputs.get("width", 512)))
                inputs["height"] = int(params.get("height", inputs.get("height", 512)))
            if class_type == "ModelSamplingSD3":
                inputs["shift"] = float(params.get("shift", inputs.get("shift", 8.0)))
            if class_type == "KSampler":
                inputs["seed"] = seed
                inputs["steps"] = steps
                inputs["cfg"] = float(params.get("cfg", inputs.get("cfg", 5.0)))
                inputs["sampler_name"] = params.get("sampler", inputs.get("sampler_name", "uni_pc"))
                inputs["scheduler"] = params.get("scheduler", inputs.get("scheduler", "simple"))
            if class_type == "KSamplerAdvanced":
                split_step = int(params.get("split_step", max(1, steps // 2)))
                inputs["steps"] = steps
                inputs["cfg"] = float(params.get("cfg", inputs.get("cfg", 3.5)))
                inputs["sampler_name"] = params.get("sampler", inputs.get("sampler_name", "euler"))
                inputs["scheduler"] = params.get("scheduler", inputs.get("scheduler", "simple"))
                if inputs.get("add_noise") == "enable":
                    inputs["noise_seed"] = seed
                    inputs["end_at_step"] = split_step
                else:
                    inputs["start_at_step"] = split_step
                    inputs["end_at_step"] = steps
    def _extract_outputs(self, history_item: dict[str, Any]) -> list[str]:
        outputs: list[str] = []
        for node_output in history_item.get("outputs", {}).values():
            for image in node_output.get("images", []):
                filename = image.get("filename")
                subfolder = image.get("subfolder", "")
                image_type = image.get("type", "output")
                if filename:
                    outputs.append(
                        f"{self.base_url}/view?filename={filename}&subfolder={subfolder}&type={image_type}"
                    )
        return outputs
