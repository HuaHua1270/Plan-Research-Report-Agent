from fastapi import FastAPI, HTTPException

from backend.Agent.src.common.web_data import ChildTaskRequest
from backend.Agent.src.controller.reporter.reporterManager import ReportTaskManager


app = FastAPI(title="Report Agent Service")

report_task_manager = ReportTaskManager()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "reporter"}


@app.post("/report/tasks")
async def create_report_task(request: ChildTaskRequest):
    task = await report_task_manager.create_task(request)
    return task.model_dump()


@app.get("/report/tasks/{task_id}")
async def get_report_task(task_id: str):
    task = await report_task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task.model_dump()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.Agent.src.controller.reporter.reporter_Controller:app",
        host="127.0.0.1",
        port=8003,
        reload=True,
    )
