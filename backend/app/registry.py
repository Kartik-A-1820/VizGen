from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .config import LOCAL_REGISTRY_PATH, REGISTRY_PATH


@dataclass(frozen=True)
class ModelConfig:
    id: str
    label: str
    family: str
    model_name: str
    task: str
    tier: str
    workflow: str
    defaults: dict[str, Any]
    launch_flags: list[str]
    paths: dict[str, str]
    ui_note: str
    tome_ratio: float
    engine: str = "comfyui"
    quant: str = ""
    vram_tier: str = "4gb"
    enabled: bool = True
    local_only: bool = False


def _parse_models(data: dict[str, Any], *, local_only: bool = False) -> list[ModelConfig]:
    models: list[ModelConfig] = []
    for item in data.get("models", []) or []:
        models.append(
            ModelConfig(
                id=str(item["id"]),
                label=str(item.get("label", item["id"])),
                family=str(item.get("family", "")),
                model_name=str(item.get("model_name", item["id"])),
                task=str(item.get("task", "generate")).lower(),
                tier=str(item.get("tier", "fast")),
                workflow=str(item.get("workflow", "")),
                defaults=dict(item.get("defaults", {})),
                launch_flags=[str(flag) for flag in item.get("launch_flags", [])],
                paths={str(key): str(value) for key, value in item.get("paths", {}).items()},
                ui_note=str(item.get("ui_note", "")),
                tome_ratio=float(item.get("tome_ratio", 0.0)),
                engine=str(item.get("engine", "comfyui")),
                quant=str(item.get("quant", "")),
                vram_tier=str(item.get("vram_tier", "4gb")),
                enabled=bool(item.get("enabled", True)),
                local_only=local_only or bool(item.get("local_only", False)),
            )
        )
    return models


def load_registry(path: Path = REGISTRY_PATH) -> list[ModelConfig]:
    """Public registry + optional gitignored local overlay (local/models_registry.local.yaml).

    Local entries append after public ones; same id overrides public (local wins).
    Overlay file is never committed — only exists on machines that create it.
    """
    by_id: dict[str, ModelConfig] = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for model in _parse_models(data, local_only=False):
            by_id[model.id] = model

    if LOCAL_REGISTRY_PATH.exists():
        local_data = yaml.safe_load(LOCAL_REGISTRY_PATH.read_text(encoding="utf-8")) or {}
        for model in _parse_models(local_data, local_only=True):
            by_id[model.id] = model

    return list(by_id.values())


def public_registry() -> list[dict[str, Any]]:
    return [
        {
            "id": model.id,
            "name": model.label,
            "label": model.label,
            "family": model.family,
            "model_name": model.model_name,
            "task": model.task,
            "tier": model.tier,
            "quant": model.quant,
            "vram_tier": model.vram_tier,
            "modes": [model.task],
            "defaults": model.defaults,
            "launch_flags": model.launch_flags,
            "paths": model.paths,
            "ui_note": model.ui_note,
            "tome_ratio": model.tome_ratio,
            "workflow": model.workflow,
            "engine": model.engine,
            "enabled": model.enabled,
            "local_only": model.local_only,
        }
        for model in load_registry()
        if model.enabled
    ]


def get_model(model_id: str) -> ModelConfig:
    for model in load_registry():
        if model.id == model_id and model.enabled:
            return model
    raise KeyError(model_id)


def get_model_for_task(task: str, model_id: str | None = None) -> ModelConfig:
    task = task.lower()
    for model in load_registry():
        if not model.enabled or model.task != task:
            continue
        if model_id is None or model.id == model_id:
            return model
    raise KeyError(model_id or task)
