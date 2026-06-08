# from __future__ import annotations
#
# import asyncio
# import logging
# import signal
# from collections.abc import Awaitable, Callable
# from contextlib import asynccontextmanager, suppress
# from typing import Any, Literal
#
# from fastapi import FastAPI
#
# from backend.Agent.src.controller.Manager.ServiceManager import ServiceManager
# from backend.Agent.src.lifecycle.lifecycle import CoreLifecycle
#
#
# RuntimeRole = Literal["api", "worker"]
# WorkerJobHandler = Callable[[dict[str, Any], ServiceManager], Awaitable[None]]
#
#
# class Launcher:
#     """Attach CoreLifecycle to FastAPI or a Redis worker process."""
#
#     def __init__(
#         self,
#         *,
#         role: RuntimeRole,
#         queue_name: str | None = None,
#         logger: logging.Logger | None = None,
#     ) -> None:
#         self.log = logger or logging.getLogger(__name__)
#         self.lifecycle = CoreLifecycle(role=role, queue_name=queue_name, logger=self.log)
#
#     @property
#     def services(self) -> ServiceManager:
#         if self.lifecycle.service_manager is None:
#             raise RuntimeError("services are not initialized")
#         return self.lifecycle.service_manager
#
#     async def start(self) -> ServiceManager:
#         return await self.lifecycle.start()
#
#     async def stop(self) -> None:
#         await self.lifecycle.stop()
#
#     @classmethod
#     def api_lifespan(cls, logger: logging.Logger | None = None):
#         @asynccontextmanager
#         async def lifespan(app: FastAPI):
#             launcher = cls(role="api", logger=logger)
#             services = await launcher.start()
#             app.state.launcher = launcher
#             app.state.services = services
#             try:
#                 yield
#             finally:
#                 await launcher.stop()
#
#         return lifespan
#
#     @classmethod
#     def worker(
#         cls,
#         *,
#         queue_name: str,
#         job_handler: WorkerJobHandler,
#         worker_name: str | None = None,
#         logger: logging.Logger | None = None,
#         poll_timeout: int = 1,
#         shutdown_timeout: float = 30.0,
#     ) -> "WorkerLauncher":
#         return WorkerLauncher(
#             queue_name=queue_name,
#             job_handler=job_handler,
#             worker_name=worker_name or queue_name,
#             logger=logger,
#             poll_timeout=poll_timeout,
#             shutdown_timeout=shutdown_timeout,
#         )
#
#
# class WorkerLauncher:
#     def __init__(
#         self,
#         *,
#         queue_name: str,
#         job_handler: WorkerJobHandler,
#         worker_name: str,
#         logger: logging.Logger | None,
#         poll_timeout: int,
#         shutdown_timeout: float,
#     ) -> None:
#         self.queue_name = queue_name
#         self.job_handler = job_handler
#         self.worker_name = worker_name
#         self.log = logger or logging.getLogger(__name__)
#         self.poll_timeout = poll_timeout
#         self.shutdown_timeout = shutdown_timeout
#
#     async def run(self) -> None:
#         stop_event = asyncio.Event()
#         self._install_signal_handlers(stop_event)
#         launcher = Launcher(role="worker", queue_name=self.queue_name, logger=self.log)
#
#         try:
#             services = await launcher.start()
#             self.log.info("%s started queue=%s", self.worker_name, self.queue_name)
#
#             while not stop_event.is_set():
#                 try:
#                     job = await services.next_job(timeout=self.poll_timeout)
#                 except asyncio.CancelledError:
#                     raise
#                 except Exception:
#                     self.log.exception("%s failed to read from queue", self.worker_name)
#                     await asyncio.sleep(1)
#                     continue
#
#                 if job is None:
#                     continue
#
#                 await self._run_job(job, services, stop_event)
#
#         finally:
#             self.log.info("%s stopping", self.worker_name)
#             await launcher.stop()
#
#     async def _run_job(
#         self,
#         job: dict[str, Any],
#         services: ServiceManager,
#         stop_event: asyncio.Event,
#     ) -> None:
#         job_task = asyncio.create_task(self.job_handler(job, services))
#         stop_task = asyncio.create_task(stop_event.wait())
#         done, pending = await asyncio.wait(
#             {job_task, stop_task},
#             return_when=asyncio.FIRST_COMPLETED,
#         )
#
#         if stop_task in done and not job_task.done():
#             self.log.info("%s waiting for current job to finish", self.worker_name)
#             try:
#                 await asyncio.wait_for(job_task, timeout=self.shutdown_timeout)
#             except Exception:
#                 self.log.exception("%s current job failed during shutdown", self.worker_name)
#             except asyncio.TimeoutError:
#                 self.log.warning("%s current job timed out during shutdown", self.worker_name)
#                 job_task.cancel()
#                 await asyncio.gather(job_task, return_exceptions=True)
#             finally:
#                 return
#
#         for task in pending:
#             task.cancel()
#         with suppress(asyncio.CancelledError):
#             await asyncio.gather(*pending)
#
#         if job_task in done:
#             try:
#                 await job_task
#             except Exception:
#                 self.log.exception("%s job failed: %s", self.worker_name, job)
#
#     def _install_signal_handlers(self, stop_event: asyncio.Event) -> None:
#         loop = asyncio.get_running_loop()
#
#         def request_stop(signum: int, *_: object) -> None:
#             self.log.info("%s received signal=%s", self.worker_name, signum)
#             loop.call_soon_threadsafe(stop_event.set)
#
#         for signum in (signal.SIGINT, signal.SIGTERM):
#             with suppress(NotImplementedError, RuntimeError, ValueError):
#                 loop.add_signal_handler(signum, stop_event.set)
#                 continue
#             with suppress(ValueError):
#                 signal.signal(signum, request_stop)
