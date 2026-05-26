from fastapi import FastAPI, HTTPException

from backend.Agent.src.common.web_data import ChildTaskRequest
from backend.Agent.src.controller.summarizer.summarizerManager import ResearchTaskManager


app = FastAPI(title="Research Agent Service")

research_task_manager = ResearchTaskManager()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "research"}


@app.post("/research/tasks")
async def create_research_task(request: ChildTaskRequest):
    task = await research_task_manager.create_task(request)
    return task.model_dump()


@app.get("/research/tasks/{task_id}")
async def get_research_task(task_id: str):
    task = await research_task_manager.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task.model_dump()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.Agent.src.controller.summarizer.summarizer_Controller:app",
        host="127.0.0.1",
        port=8002,
        reload=True,
    )
