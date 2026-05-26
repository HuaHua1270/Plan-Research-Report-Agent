from fastapi import FastAPI, HTTPException

from backend.Agent.src.common.web_data import ChildTaskRequest
from backend.Agent.src.controller.planner.plannerManager import PlannerTaskManager


app = FastAPI(title="Planner Agent Service")

planner_task_manager = PlannerTaskManager()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "planner"}


@app.post("/planner/tasks")
async def create_planner_task(request: ChildTaskRequest):
    task = await planner_task_manager.create_task(request)
    return task.model_dump()


@app.get("/planner/tasks/{task_id}")
async def get_planner_task(task_id: str):
    task = await planner_task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task.model_dump()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.Agent.src.controller.planner.planner_Controller:app",
        host="127.0.0.1",
        port=8001,
        reload=True,
    )

