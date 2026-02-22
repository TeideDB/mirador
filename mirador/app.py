"""FastAPI entry point for Mirador."""

import os
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from teide import TeideLib

from mirador import __version__
from mirador.api.dashboards import router as dashboards_router
from mirador.api.dependencies import router as dependencies_router
from mirador.api.files import router as files_router
from mirador.api.nodes import router as nodes_router
from mirador.api.pipelines import router as pipelines_router
from mirador.api.projects import router as projects_router
from mirador.api.ws import router as ws_router
from mirador.api.ws_dashboard import router as ws_dashboard_router

_teide: TeideLib | None = None


def get_teide() -> TeideLib:
    """Return the initialized TeideLib instance. Asserts it has been set up."""
    assert _teide is not None, "TeideLib not initialized — lifespan not started"
    return _teide


_publish_registry = None


def get_publish_registry():
    global _publish_registry
    if _publish_registry is None:
        from mirador.engine.publish_registry import PublishRegistry
        _publish_registry = PublishRegistry()
    return _publish_registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Restore user-installed Python packages from data volume
    req_file = Path(os.environ.get("MIRADOR_DATA_DIR", "mirador_data")) / "requirements.txt"
    if req_file.exists() and req_file.stat().st_size > 0:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", str(req_file)],
            check=False,
        )

    global _teide
    lib_path = os.environ.get("TEIDE_LIB")
    _teide = TeideLib(lib_path=lib_path)
    _teide.sym_init()
    _teide.arena_init()

    from mirador.engine.scheduler import start_scheduler, stop_scheduler
    await start_scheduler()

    # Restore published streaming pipelines
    import logging
    _logger = logging.getLogger(__name__)

    global _publish_registry
    from mirador.engine.publish_registry import PublishRegistry
    _publish_registry = PublishRegistry()

    from mirador.storage.projects import ProjectStore
    from mirador.engine.streaming_executor import StreamingExecutor
    from mirador.engine.table_env import TableEnv
    from mirador.api.nodes import get_registry as get_node_registry
    from mirador.api.ws_dashboard import notify_data_changed

    store = ProjectStore()
    for proj in store.list_projects():
        slug = proj["slug"]
        for name in store.list_pipelines(slug):
            pipeline = store.load_pipeline(slug, name)
            if pipeline and pipeline.get("published"):
                key = f"{slug}/{name}"
                try:
                    env = TableEnv()
                    node_reg = get_node_registry()
                    executor = StreamingExecutor(node_reg)

                    def on_tick(tick_env, k=key):
                        notify_data_changed(k, tick_env.list())

                    from mirador.api.pipelines import _unwrap_reactflow
                    exec_pipeline = _unwrap_reactflow(pipeline)
                    executor.start(exec_pipeline, env, on_tick_complete=on_tick)
                    _publish_registry.register(key, env, executor)
                    _logger.info("Restored published pipeline: %s", key)
                except Exception as exc:
                    _logger.error("Failed to restore pipeline %s: %s", key, exc)

    try:
        yield
    finally:
        await stop_scheduler()
        # Stop all published pipelines
        if _publish_registry:
            for key in _publish_registry.list_running():
                entry = _publish_registry.unregister(key)
                if entry and entry["executor"]:
                    entry["executor"].stop()
        _teide.pool_destroy()
        _teide.sym_destroy()
        _teide.arena_destroy_all()
        _teide = None


app = FastAPI(title="Mirador", version=__version__, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(dashboards_router)
app.include_router(dependencies_router)
app.include_router(files_router)
app.include_router(nodes_router)
app.include_router(pipelines_router)
app.include_router(projects_router)
app.include_router(ws_router)
app.include_router(ws_dashboard_router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": __version__, "teide": _teide is not None}


# Serve frontend static files (MUST be after all API routes)
_frontend_dir = Path(__file__).parent / "frontend_dist"
if _frontend_dir.exists():

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve the React SPA — catch-all for non-API routes."""
        file_path = _frontend_dir / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_frontend_dir / "index.html")


def main():
    import uvicorn

    uvicorn.run("mirador.app:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
