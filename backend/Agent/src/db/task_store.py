from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.Agent.src.common.DO.Task import (
    ParentTask,
    PlannerChildTask,
    ReportChildTask,
    ResearchChildTask,
)
from backend.Agent.src.db.config import DEFAULT_SCHEMA_FILE


ChildTask = PlannerChildTask | ResearchChildTask | ReportChildTask


class TaskStore:
    """父任务和子任务的 SQLite 持久化层。

    Manager 只通过 TaskStore 读写数据库，避免业务流程里散落 SQL。
    当前 schema 不强行限制 parent+stage 唯一，因为 Researcher 阶段需要为同一个
    parent 创建多条 RESEARCH 子任务。
    """

    def __init__(self, conn, schema_file: str | Path = DEFAULT_SCHEMA_FILE):
        self.conn = conn
        self.schema_file = Path(schema_file)
        self.ensure_schema()

    def ensure_schema(self) -> None:
        # 建表脚本可以重复执行；SQLite 的 IF NOT EXISTS 保证启动时幂等初始化。
        schema_sql = self.schema_file.read_text(encoding="utf-8")
        if not schema_sql.strip():
            return
        self.conn.executescript(schema_sql)
        self.conn.commit()

    def insert_parent_task(self, task: ParentTask) -> None:
        # Parent 一创建就落库，后续即使 Redis 投递失败，也可以通过数据库恢复/排查。
        self._execute(
            """
            INSERT INTO parent_tasks (
                task_id, status, current_stage, topic, language, depth,
                max_subtopics, need_citations, report_format, user_id,
                planner_task_id, research_task_id, reporter_task_id,
                plan_json, research_json, report_text, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.task_id,
                task.status,
                task.current_stage,
                task.topic,
                task.language,
                task.depth,
                task.max_subtopics,
                int(task.need_citations),
                task.report_format,
                task.user_id,
                task.planner_task_id,
                task.research_task_id,
                task.reporter_task_id,
                self._to_json(task.plan_json),
                self._to_json(task.research_json),
                task.report_text,
                task.error,
            ),
        )

    def insert_child_task(self, task: ChildTask) -> None:
        # Planner/Reporter 通常每个 parent 一条；Researcher 可以按 subtopic 多条。
        self._execute(
            """
            INSERT INTO child_tasks (
                task_id, parent_task_id, stage, status, input_data, result, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.task_id,
                task.parent_task_id,
                task.stage,
                task.status,
                self._to_json(task.input_data),
                self._to_json(task.result),
                task.error,
            ),
        )

    def update_child_status(self, task_id: str, status: str) -> None:
        self._execute(
            """
            UPDATE child_tasks
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
            """,
            (status, task_id),
        )

    def update_child_result(self, task_id: str, result: dict[str, Any]) -> None:
        self._execute(
            """
            UPDATE child_tasks
            SET status = 'DONE', result = ?, error = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
            """,
            (self._to_json(result), task_id),
        )

    def update_child_error(self, task_id: str, error: str) -> None:
        self._execute(
            """
            UPDATE child_tasks
            SET status = 'FAILED', error = ?, updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
            """,
            (error, task_id),
        )

    def update_parent_stage(self, task_id: str, current_stage: str, status: str | None = None) -> None:
        if status is None:
            self._execute(
                """
                UPDATE parent_tasks
                SET current_stage = ?, updated_at = CURRENT_TIMESTAMP
                WHERE task_id = ?
                """,
                (current_stage, task_id),
            )
            return

        self._execute(
            """
            UPDATE parent_tasks
            SET current_stage = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
            """,
            (current_stage, status, task_id),
        )

    def update_parent_result(
        self,
        task_id: str,
        *,
        plan_json: dict[str, Any] | None = None,
        research_json: dict[str, Any] | None = None,
        report_text: str | None = None,
        current_stage: str | None = None,
        status: str | None = None,
    ) -> None:
        updates: list[str] = []
        params: list[Any] = []

        if plan_json is not None:
            updates.append("plan_json = ?")
            params.append(self._to_json(plan_json))
        if research_json is not None:
            updates.append("research_json = ?")
            params.append(self._to_json(research_json))
        if report_text is not None:
            updates.append("report_text = ?")
            params.append(report_text)
        if current_stage is not None:
            updates.append("current_stage = ?")
            params.append(current_stage)
        if status is not None:
            updates.append("status = ?")
            params.append(status)

        if not updates:
            return

        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(task_id)
        self._execute(
            f"UPDATE parent_tasks SET {', '.join(updates)} WHERE task_id = ?",
            tuple(params),
        )

    def update_parent_error(self, task_id: str, error: str) -> None:
        self._execute(
            """
            UPDATE parent_tasks
            SET status = 'FAILED', error = ?, updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
            """,
            (error, task_id),
        )

    def update_parent_child_id(self, task_id: str, stage: str, child_task_id: str) -> None:
        # research_task_id 只保存第一条 Research 子任务 ID 作为兼容字段。
        # 多 Research 子任务的完整列表应通过 list_child_tasks(parent, "RESEARCH") 查询。
        column_by_stage = {
            "PLANNER": "planner_task_id",
            "RESEARCH": "research_task_id",
            "REPORTER": "reporter_task_id",
        }
        column = column_by_stage[stage]
        self._execute(
            f"""
            UPDATE parent_tasks
            SET {column} = ?, updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
            """,
            (child_task_id, task_id),
        )

    def get_parent_task(self, task_id: str) -> ParentTask | None:
        row = self._fetch_one("SELECT * FROM parent_tasks WHERE task_id = ?", (task_id,))
        if row is None:
            return None

        return self._row_to_parent_task(row)

    def get_child_task(self, task_id: str) -> ChildTask | None:
        row = self._fetch_one("SELECT * FROM child_tasks WHERE task_id = ?", (task_id,))
        if row is None:
            return None

        return self._row_to_child_task(row)

    def get_latest_child_task(self, parent_task_id: str, stage: str) -> ChildTask | None:
        # 按父任务和阶段查询最新子任务，用于处理 Redis 重复消息时做幂等判断。
        row = self._fetch_one(
            """
            SELECT *
            FROM child_tasks
            WHERE parent_task_id = ? AND stage = ?
            ORDER BY updated_at DESC, created_at DESC, task_id DESC
            LIMIT 1
            """,
            (parent_task_id, stage),
        )
        if row is None:
            return None
        return self._row_to_child_task(row)

    def list_child_tasks(self, parent_task_id: str, stage: str) -> list[ChildTask]:
        # 按父任务查询某阶段的全部子任务；Research 拆分后同一个父任务会有多条 RESEARCH 记录。
        rows = self._fetch_all(
            """
            SELECT *
            FROM child_tasks
            WHERE parent_task_id = ? AND stage = ?
            ORDER BY created_at ASC, updated_at ASC, task_id ASC
            """,
            (parent_task_id, stage),
        )
        return [self._row_to_child_task(row) for row in rows]

    def list_recoverable_child_tasks(self, stage: str) -> list[ChildTask]:
        # 启动恢复只处理“执行中/待执行且没有结果”的子任务，不自动恢复 FAILED。
        rows = self._fetch_all(
            """
            SELECT *
            FROM child_tasks
            WHERE stage = ?
              AND status IN ('PENDING', 'RUNNING')
              AND result IS NULL
            ORDER BY updated_at ASC, created_at ASC, task_id ASC
            """,
            (stage,),
        )
        return [self._row_to_child_task(row) for row in rows]

    def list_recoverable_parents(self, stage: str) -> list[ParentTask]:
        # 父任务停在某阶段时，如果缺少该阶段子任务，需要由对应 worker 补建。
        rows = self._fetch_all(
            """
            SELECT *
            FROM parent_tasks
            WHERE status = 'RUNNING' AND current_stage = ?
            ORDER BY updated_at ASC, created_at ASC, task_id ASC
            """,
            (stage,),
        )
        return [self._row_to_parent_task(row) for row in rows]

    def _row_to_parent_task(self, row: dict[str, Any]) -> ParentTask:
        return ParentTask(
            task_id=row["task_id"],
            status=row["status"],
            current_stage=row["current_stage"],
            topic=row["topic"],
            language=row["language"],
            depth=row["depth"],
            max_subtopics=row["max_subtopics"],
            need_citations=bool(row["need_citations"]),
            report_format=row["report_format"],
            user_id=row["user_id"],
            planner_task_id=row["planner_task_id"],
            research_task_id=row["research_task_id"],
            reporter_task_id=row["reporter_task_id"],
            plan_json=self._from_json(row["plan_json"]),
            research_json=self._from_json(row["research_json"]),
            report_text=row["report_text"],
            error=row["error"],
        )

    def _row_to_child_task(self, row: dict[str, Any]) -> ChildTask:
        task_cls = {
            "PLANNER": PlannerChildTask,
            "RESEARCH": ResearchChildTask,
            "REPORTER": ReportChildTask,
        }[row["stage"]]
        return task_cls(
            task_id=row["task_id"],
            parent_task_id=row["parent_task_id"],
            stage=row["stage"],
            status=row["status"],
            input_data=self._from_json(row["input_data"]) or {},
            result=self._from_json(row["result"]),
            error=row["error"],
        )

    def _execute(self, sql: str, params: tuple[Any, ...]) -> None:
        cursor = None
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql, params)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        finally:
            if cursor is not None:
                cursor.close()

    def _fetch_one(self, sql: str, params: tuple[Any, ...]):
        cursor = self.conn.cursor()
        try:
            cursor.execute(sql, params)
            row = cursor.fetchone()
            if row is None:
                return None
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, row))
        finally:
            cursor.close()

    def _fetch_all(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        cursor = self.conn.cursor()
        try:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        finally:
            cursor.close()

    def _to_json(self, value: Any) -> str | None:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)

    def _from_json(self, value: str | None) -> Any:
        if value is None:
            return None
        return json.loads(value)
