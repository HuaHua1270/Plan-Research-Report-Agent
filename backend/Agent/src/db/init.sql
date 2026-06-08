CREATE TABLE IF NOT EXISTS parent_tasks (
    task_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    current_stage TEXT NOT NULL,
    topic TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'zh',
    depth TEXT NOT NULL DEFAULT 'standard',
    max_subtopics INTEGER NOT NULL DEFAULT 5,
    need_citations INTEGER NOT NULL DEFAULT 1,
    report_format TEXT NOT NULL DEFAULT 'markdown',
    user_id TEXT,
    planner_task_id TEXT,
    research_task_id TEXT,
    reporter_task_id TEXT,
    plan_json TEXT,
    research_json TEXT,
    report_text TEXT,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS child_tasks (
    task_id TEXT PRIMARY KEY,
    parent_task_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    input_data TEXT NOT NULL,
    result TEXT,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(parent_task_id) REFERENCES parent_tasks(task_id)
);

CREATE INDEX IF NOT EXISTS idx_child_tasks_parent_stage
ON child_tasks(parent_task_id, stage);

CREATE INDEX IF NOT EXISTS idx_child_tasks_status_stage
ON child_tasks(status, stage);
