"""Dependencies API — install/uninstall Python packages at runtime."""

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/dependencies", tags=["dependencies"])


def _requirements_path() -> Path:
    data_dir = Path(os.environ.get("MIRADOR_DATA_DIR", "mirador_data"))
    return data_dir / "requirements.txt"


def _read_requirements() -> list[str]:
    path = _requirements_path()
    if not path.exists():
        return []
    lines = path.read_text().strip().splitlines()
    return [l.strip() for l in lines if l.strip() and not l.startswith("#")]


def _write_requirements(packages: list[str]) -> None:
    path = _requirements_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sorted(set(packages))) + "\n" if packages else "")


@router.get("")
def list_dependencies():
    """List currently installed custom packages."""
    return {"packages": _read_requirements()}


class PackageRequest(BaseModel):
    packages: list[str]


@router.post("/install")
def install_packages(body: PackageRequest):
    """Install packages via pip, streaming output as SSE."""
    packages = [p.strip() for p in body.packages if p.strip()]
    if not packages:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'message': 'No packages specified'})}\n\n"]),
            media_type="text/event-stream",
        )

    event_queue: queue.Queue[dict | None] = queue.Queue()

    def run_pip():
        try:
            cmd = [sys.executable, "-m", "pip", "install"] + packages
            event_queue.put({"type": "log", "message": f"$ {' '.join(cmd)}"})
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            for line in proc.stdout:
                event_queue.put({"type": "log", "message": line.rstrip()})
            proc.wait()

            if proc.returncode == 0:
                current = _read_requirements()
                current.extend(packages)
                _write_requirements(current)
                event_queue.put({"type": "done", "status": "ok"})
            else:
                event_queue.put({"type": "done", "status": "error",
                                 "message": f"pip exited with code {proc.returncode}"})
        except Exception as exc:
            event_queue.put({"type": "done", "status": "error", "message": str(exc)})
        finally:
            event_queue.put(None)

    threading.Thread(target=run_pip, daemon=True).start()

    def stream():
        while True:
            event = event_queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/uninstall")
def uninstall_packages(body: PackageRequest):
    """Uninstall packages via pip, streaming output as SSE."""
    packages = [p.strip() for p in body.packages if p.strip()]
    if not packages:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'message': 'No packages specified'})}\n\n"]),
            media_type="text/event-stream",
        )

    # Strip version specifiers for uninstall (pip uninstall uses bare names)
    bare_names = []
    for p in packages:
        for sep in [">=", "<=", "==", "!=", "~=", ">", "<"]:
            if sep in p:
                p = p.split(sep)[0]
                break
        bare_names.append(p.strip())

    event_queue: queue.Queue[dict | None] = queue.Queue()

    def run_pip():
        try:
            cmd = [sys.executable, "-m", "pip", "uninstall", "-y"] + bare_names
            event_queue.put({"type": "log", "message": f"$ {' '.join(cmd)}"})
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            for line in proc.stdout:
                event_queue.put({"type": "log", "message": line.rstrip()})
            proc.wait()

            if proc.returncode == 0:
                current = _read_requirements()
                # Remove matching packages (compare bare names)
                remaining = []
                for pkg in current:
                    pkg_name = pkg
                    for sep in [">=", "<=", "==", "!=", "~=", ">", "<"]:
                        if sep in pkg_name:
                            pkg_name = pkg_name.split(sep)[0]
                            break
                    if pkg_name.strip().lower() not in [n.lower() for n in bare_names]:
                        remaining.append(pkg)
                _write_requirements(remaining)
                event_queue.put({"type": "done", "status": "ok"})
            else:
                event_queue.put({"type": "done", "status": "error",
                                 "message": f"pip exited with code {proc.returncode}"})
        except Exception as exc:
            event_queue.put({"type": "done", "status": "error", "message": str(exc)})
        finally:
            event_queue.put(None)

    threading.Thread(target=run_pip, daemon=True).start()

    def stream():
        while True:
            event = event_queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
