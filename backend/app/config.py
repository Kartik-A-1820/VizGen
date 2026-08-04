from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
REGISTRY_PATH = BACKEND_DIR / "models_registry.yaml"
# Gitignored machine-only overlay (see local/models_registry.local.yaml)
LOCAL_REGISTRY_PATH = PROJECT_DIR / "local" / "models_registry.local.yaml"
WORKFLOWS_DIR = BACKEND_DIR / "workflows"
FRONTEND_DIR = PROJECT_DIR / "frontend"
DATA_DIR = PROJECT_DIR / "data"
OUTPUTS_DIR = PROJECT_DIR / "outputs"
DB_PATH = DATA_DIR / "imagegen.sqlite3"

COMFYUI_URL = "http://127.0.0.1:8188"


def ensure_runtime_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
