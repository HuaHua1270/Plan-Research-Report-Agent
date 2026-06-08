# from __future__ import annotations
#
# import logging
# from typing import Callable, Literal
#
# from backend.Agent.src.config import Settings
# from backend.Agent.src.controller.Manager.ServiceManager import ServiceManager
#
#
# LifecycleState = Literal["created", "initialized", "started", "stopping", "stopped"]
# RuntimeRole = Literal["api", "worker"]
# ServiceManagerFactory = Callable[..., ServiceManager]
#
#
# class CoreLifecycle:
#     """Small lifecycle state machine around process-local services."""
#
#     def __init__(
#         self,
#         *,
#         role: RuntimeRole,
#         queue_name: str | None = None,
#         settings: Settings | None = None,
#         logger: logging.Logger | None = None,
#         service_manager_factory: ServiceManagerFactory = ServiceManager,
#     ) -> None:
#         self.role = role
#         self.queue_name = queue_name
#         self.settings = settings
#         self.log = logger or logging.getLogger(__name__)
#         self._service_manager_factory = service_manager_factory
#         self.service_manager: ServiceManager | None = None
#         self.state: LifecycleState = "created"
#
#     async def initialize(self) -> None:
#         if self.state in {"initialized", "started"}:
#             return
#         if self.state == "stopping":
#             raise RuntimeError("cannot initialize while lifecycle is stopping")
#
#         self.service_manager = self._service_manager_factory(
#             role=self.role,
#             queue_name=self.queue_name,
#             settings=self.settings,
#             logger=self.log,
#         )
#         self.state = "initialized"
#
#     async def start(self) -> ServiceManager:
#         if self.state == "started":
#             if self.service_manager is None:
#                 raise RuntimeError("lifecycle is started without a service manager")
#             return self.service_manager
#
#         if self.state == "created":
#             await self.initialize()
#         if self.state != "initialized" or self.service_manager is None:
#             raise RuntimeError(f"cannot start lifecycle from state={self.state}")
#
#         try:
#             await self.service_manager.start()
#             self.state = "started"
#             return self.service_manager
#         except BaseException:
#             self.log.exception("lifecycle startup failed; cleaning up")
#             await self.stop()
#             raise
#
#     async def stop(self) -> None:
#         if self.state == "stopped":
#             return
#
#         self.state = "stopping"
#         try:
#             if self.service_manager is not None:
#                 await self.service_manager.stop()
#         finally:
#             self.state = "stopped"
#
