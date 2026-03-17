"""
MISI BAYANG — startup script with LLM provider selection.

Usage examples:
    # Remote LLM from .env (default)
    python run.py

    # Local LLM via ramalama (start it first with: ramalama serve --ngl 0 llama3.2:3b)
    python run.py --local

    # Local LLM with explicit URL (ramalama serves OpenAI-compatible API at /v1)
    python run.py --local --llm-url http://localhost:8080/v1 --model llama3.2:3b

    # Custom backend port
    python run.py --port 9000

    # Dev mode with auto-reload
    python run.py --local --reload
"""

from __future__ import annotations

import argparse
import os


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the MISI BAYANG SAR Mission Control API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ── LLM provider ─────────────────────────────────────────────────────
    llm_group = parser.add_mutually_exclusive_group()
    llm_group.add_argument(
        "--local",
        action="store_true",
        help="Use a local LLM via Ollama-compatible API (ramalama, ollama, etc.)",
    )
    llm_group.add_argument(
        "--remote",
        action="store_true",
        help="Use remote LLM from .env (MODEL_KEY / MODEL_BASE_URL). This is the default.",
    )

    parser.add_argument(
        "--llm-url",
        default=None,
        metavar="URL",
        help=(
            "Override the LLM base URL. Default when --local: http://localhost:8080/v1"
        ),
    )
    parser.add_argument(
        "--model",
        default=None,
        metavar="NAME",
        help="Override the model name. Default when --local: llama3.2:3b",
    )

    # ── Server ────────────────────────────────────────────────────────────
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for the backend HTTP server (default: 8000)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload on source changes (development mode)",
    )

    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    # ── Apply LLM overrides BEFORE importing app ──────────────────────────
    # pydantic-settings reads os.environ at import time; setting these here
    # means the .env file is used as fallback, CLI flags take priority.
    if args.local:
        os.environ["USE_LOCAL_LLM"] = "true"
        # Only set defaults — don't overwrite if user also passed --llm-url/--model
        os.environ.setdefault("MODEL_BASE_URL", "http://localhost:8080/v1")
        os.environ.setdefault("MODEL_NAME", "llama3.2:3b")

    if args.llm_url:
        os.environ["MODEL_BASE_URL"] = args.llm_url

    if args.model:
        os.environ["MODEL_NAME"] = args.model

    # ── Config summary ────────────────────────────────────────────────────
    use_local = os.environ.get("USE_LOCAL_LLM", "false").lower() in ("true", "1", "yes")
    model = os.environ.get("MODEL_NAME", "qwen/qwen3-235b-a22b")
    llm_url = os.environ.get("MODEL_BASE_URL", "https://openrouter.ai/api/v1")

    print("=" * 52)
    print("  MISI BAYANG — SAR Mission Control")
    print("=" * 52)
    print(
        f"  LLM mode  : {'local (Ollama-compatible)' if use_local else 'remote (OpenRouter)'}"
    )
    print(f"  Model     : {model}")
    print(f"  LLM URL   : {llm_url}")
    print(f"  Server    : http://{args.host}:{args.port}")
    print("=" * 52)
    print()

    # ── Start uvicorn ─────────────────────────────────────────────────────
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
