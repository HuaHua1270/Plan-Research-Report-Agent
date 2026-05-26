from __future__ import annotations

import argparse
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    app: str
    port: int


SERVICES = [
    ServiceSpec("task-manager", "backend.Agent.src.main:app", 8000),
    ServiceSpec("planner", "backend.Agent.src.controller.planner.planner_Controller:app", 8001),
    ServiceSpec("research", "backend.Agent.src.controller.summarizer.summarizer_Controller:app", 8002),
    ServiceSpec("reporter", "backend.Agent.src.controller.reporter.reporter_Controller:app", 8003),
]


def build_command(service: ServiceSpec, reload: bool = False) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        service.app,
        "--host",
        "127.0.0.1",
        "--port",
        str(service.port),
    ]
    if reload:
        cmd.append("--reload")
    return cmd


def start_service(service: ServiceSpec, reload: bool = False) -> subprocess.Popen:
    cmd = build_command(service, reload=reload)
    print(f"starting {service.name}: http://127.0.0.1:{service.port}")
    print(f"  reload={'enabled' if reload else 'disabled'}")
    return subprocess.Popen(cmd, cwd=Path(__file__).resolve().parents[2])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start Agent backend services.")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn reload. This can reset in-memory task state when files change.",
    )
    parser.add_argument(
        "--only",
        choices=[service.name for service in SERVICES],
        help="Start only one service.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    services = [service for service in SERVICES if args.only is None or service.name == args.only]
    processes: list[subprocess.Popen] = []

    def shutdown(*_: object) -> None:
        print("\nstopping services...")
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    for service in services:
        processes.append(start_service(service, reload=args.reload))

    print("\nservices started. press Ctrl+C to stop.")
    for process in processes:
        process.wait()


if __name__ == "__main__":
    main()
