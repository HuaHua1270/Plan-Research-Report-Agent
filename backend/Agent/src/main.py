from fastapi import FastAPI, HTTPException

from backend.Agent.src.Manager.TaskManager import TaskManager
from backend.Agent.src.common.web_data import ResearchTaskRequest, ChildTaskCallback

app = FastAPI()

task_manager = TaskManager()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "task-manager"}

@app.post("/research-tasks")
async def create_research_task(request: ResearchTaskRequest):

    task = await task_manager.create_task(request)

    return {
        "task_id": task.task_id,
        "status": task.status,
    }


# 前端获取结果接口
@app.get("/research-tasks/{task_id}")
async def get_research_task(task_id: str):
    task = await task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task

@app.post("/internal/callbacks/planner")
async def planner_callback(callback: ChildTaskCallback):
    return await task_manager.handle_planner_callback(callback)

@app.post("/internal/callbacks/research")
async def research_callback(callback: ChildTaskCallback):
    return await task_manager.handle_research_callback(callback)

@app.post("/internal/callbacks/reporter")
async def reporter_callback(callback: ChildTaskCallback):
    return await task_manager.handle_reporter_callback(callback)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.Agent.src.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
