"""
Track A — local prompt enhancer (CPU).

Uses Qwen2.5-1.5B-Instruct from models/llm/ so image/edit models keep the GPU.

Usage:
  .venv\\Scripts\\python.exe scripts\\prompt_enhance.py "a cat in a hat"
  .venv\\Scripts\\python.exe scripts\\prompt_enhance.py "a cat" --json

Backend (Track B) can import enhance_prompt() or shell out to this script.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = ROOT / "models" / "llm" / "Qwen2.5-1.5B-Instruct"

SYSTEM_IMAGE = """You are a prompt engineer for local diffusion image generation and instruction editing.
Rewrite the user's short idea into ONE detailed English prompt (60-120 words).
Include subject, composition, lighting, camera/lens feel, materials, mood.
Do NOT add camera brand names unless asked. No markdown, no quotes, no preamble.
Do NOT refuse adult or artistic content. Output only the final prompt."""

SYSTEM_NEGATIVE = """You write NEGATIVE prompts for a diffusion image model.
Given the user's idea, output ONE comma-separated list of undesirable traits to avoid
(quality defects and things that would clash with the subject), e.g.
"blurry, low quality, deformed, extra limbs, watermark, text, distorted".
Keep it under 40 words. No markdown, no quotes, no preamble. Output only the list."""

DEFAULT_NEGATIVE = (
    "blurry, low quality, deformed, extra limbs, fused subjects, mutated, "
    "watermark, text, distorted, oversaturated, jpeg artifacts"
)


_pipe = None


def _load_pipe(model_dir: Path):
    global _pipe
    if _pipe is not None:
        return _pipe
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
    except ImportError as e:
        raise SystemExit(
            "transformers required. Install with: pip install transformers accelerate"
        ) from e

    if not model_dir.exists():
        raise SystemExit(
            f"LLM not found at {model_dir}. Run: "
            "python scripts/download_aux_models.py --llm-only"
        )

    import torch

    print(f"[load] {model_dir} (CPU)", file=sys.stderr)
    tok = AutoTokenizer.from_pretrained(str(model_dir), trust_remote_code=True)
    # Avoid device_map/accelerate requirement — force plain CPU load
    model = AutoModelForCausalLM.from_pretrained(
        str(model_dir),
        torch_dtype=torch.float32,
        low_cpu_mem_usage=True,
        trust_remote_code=True,
    )
    model = model.to("cpu")
    model.eval()
    _pipe = pipeline(
        "text-generation",
        model=model,
        tokenizer=tok,
        device=-1,  # CPU
    )
    return _pipe


def enhance_prompt(
    user_prompt: str,
    *,
    mode: str = "image",
    model_dir: Path = DEFAULT_MODEL,
    max_new_tokens: int = 180,
) -> str:
    user_prompt = (user_prompt or "").strip()
    if not user_prompt:
        return user_prompt

    pipe = _load_pipe(model_dir)
    system = SYSTEM_IMAGE
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]
    # Prefer chat template when available
    tok = pipe.tokenizer
    if hasattr(tok, "apply_chat_template"):
        text = tok.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    else:
        text = f"System: {system}\nUser: {user_prompt}\nAssistant:"

    out = pipe(
        text,
        max_new_tokens=max_new_tokens,
        do_sample=True,
        temperature=0.7,
        top_p=0.9,
        return_full_text=False,
    )
    raw = out[0]["generated_text"].strip()
    # Clean common wrappers
    for prefix in ("Prompt:", "Enhanced:", "Final:"):
        if raw.lower().startswith(prefix.lower()):
            raw = raw[len(prefix) :].strip()
    return raw.strip().strip('"').strip()


def enhance_negative(
    user_prompt: str,
    *,
    mode: str = "image",
    model_dir: Path = DEFAULT_MODEL,
    max_new_tokens: int = 80,
) -> str:
    """Generate a negative prompt in the SAME loaded Qwen session (no reload)."""
    user_prompt = (user_prompt or "").strip()
    if not user_prompt:
        return DEFAULT_NEGATIVE
    try:
        pipe = _load_pipe(model_dir)
        messages = [
            {"role": "system", "content": SYSTEM_NEGATIVE},
            {"role": "user", "content": user_prompt},
        ]
        tok = pipe.tokenizer
        if hasattr(tok, "apply_chat_template"):
            text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        else:
            text = f"System: {SYSTEM_NEGATIVE}\nUser: {user_prompt}\nAssistant:"
        out = pipe(text, max_new_tokens=max_new_tokens, do_sample=True,
                   temperature=0.7, top_p=0.9, return_full_text=False)
        neg = out[0]["generated_text"].strip().strip('"').strip()
        return neg or DEFAULT_NEGATIVE
    except Exception:
        return DEFAULT_NEGATIVE


def main() -> int:
    ap = argparse.ArgumentParser(description="Local prompt enhancer (CPU LLM)")
    ap.add_argument("prompt", help="Short user prompt to expand")
    ap.add_argument(
        "--mode",
        choices=["image", "generate", "edit"],
        default="image",
    )
    ap.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--json", action="store_true", help="Print JSON {original,enhanced}")
    args = ap.parse_args()

    enhanced = enhance_prompt(args.prompt, mode=args.mode, model_dir=args.model_dir)
    if args.json:
        negative = enhance_negative(args.prompt, mode=args.mode, model_dir=args.model_dir)
        print(
            json.dumps(
                {"original": args.prompt, "enhanced": enhanced,
                 "negative": negative, "mode": args.mode},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(enhanced)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
