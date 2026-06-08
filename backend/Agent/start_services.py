from __future__ import annotations

import argparse
import signal
import subprocess
import sys
from pathlib import Path


API_TARGET = "backend.Agent.src.main:app"
API_HOST = "127.0.0.1"
API_PORT = 8000


def build_command(reload: bool = False) -> list[str]:
    """构造唯一启动命令。

    当前项目已经改成单 main.py 模式：FastAPI API、Planner consumer、
    Researcher consumer、Reporter consumer 都在 backend.Agent.src.main:app
    的 lifespan 中启动，因此这里不再额外拉起 worker 子进程。
    """

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        API_TARGET,
        "--host",
        API_HOST,
        "--port",
        str(API_PORT),
    ]
    if reload:
        cmd.append("--reload")
    return cmd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start Agent backend with one main.py process.")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn reload for development.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    process: subprocess.Popen | None = None

    def shutdown(*_: object) -> None:
        """转发退出信号给 uvicorn。

        真正的资源释放由 main.py 的 FastAPI lifespan 完成：它会先停止三个
        consumer，再关闭 Redis 和 SQLite。
        """

        if process is not None and process.poll() is None:
            print("\nstopping agent main service...")
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    cmd = build_command(reload=args.reload)
    print(f"starting agent main service: http://{API_HOST}:{API_PORT}")
    print(f"  target={API_TARGET}")
    print(f"  reload={'enabled' if args.reload else 'disabled'}")

    # cwd 放到项目根目录，保证 backend.Agent.src... 绝对导入可以稳定解析。
    process = subprocess.Popen(cmd, cwd=Path(__file__).resolve().parents[2])
    process.wait()


if __name__ == "__main__":
    main()
