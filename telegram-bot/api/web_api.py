import logging
from typing import Union

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from db.database import init_db
from models import (
    Config,
    Group,
    Stats,
    TaskAddExecutors,
    TaskCreate,
    TaskGroup,
    TaskGroupUpdate,
    TaskStatusUpdate,
    User,
)
from repositories.config_repository import ConfigRepository
from repositories.groups_repository import GroupsRepository
from repositories.stats_repository import StatsRepository
from repositories.tasks_repository import TasksRepository
from repositories.users_repository import UsersRepository


class GroupOperationRequest(TaskGroupUpdate):
    group_operation: bool


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

repository = TasksRepository()
users_repo = UsersRepository()
groups_repo = GroupsRepository()
config_repo = ConfigRepository()
stats_repo = StatsRepository()


@app.on_event("startup")
def startup_event() -> None:
    init_db()


@app.get("/api/tasks")
def get_tasks() -> dict:
    tasks = repository.get_all_tasks()
    groups = repository.get_task_groups_with_tasks()
    return {
        "tasks": [t.model_dump() for t in tasks],
        "groups": [g.model_dump() for g in groups],
    }


@app.get("/api/users")
def get_users() -> dict:
    users = users_repo.get_all_users()
    return {"users": [u.model_dump() for u in users]}


class UserPayload(User):
    groups: list[str] = []


@app.post("/api/users")
def create_or_update_user(payload: UserPayload) -> dict:
    user = users_repo.upsert_user(payload.username, payload.full_name, payload.groups)
    return {"success": True, "user": user}


@app.put("/api/users/{username}")
def update_user(username: str, payload: UserPayload) -> dict:
    try:
        user = users_repo.update_user(username, payload.full_name, payload.groups)
        return {"success": True, "user": user}
    except ValueError as exc:
        logging.exception("User %s not found", username)
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/groups")
def get_groups() -> dict:
    groups = groups_repo.get_all_groups()
    return {"groups": [g.model_dump() for g in groups]}


@app.post("/api/groups")
def create_or_update_group(group: Group) -> dict:
    saved = groups_repo.create_or_update_group(group.id, group.name)
    return {"success": True, "group": saved}


@app.get("/api/config")
def get_config() -> Config:
    return config_repo.get_config()


class ConfigPayload(Config):
    pass


@app.post("/api/config")
def set_config(payload: ConfigPayload) -> Config:
    cfg = Config(**payload.model_dump())
    return config_repo.set_config(cfg)


@app.get("/api/stats")
def get_stats() -> Stats:
    return stats_repo.get_stats()


@app.post("/api/tasks")
def create_or_add_tasks(
    payload: Union[TaskCreate, TaskAddExecutors] = Body(...),
) -> dict:
    try:
        if isinstance(payload, TaskCreate) or getattr(payload, "group_task_id", None) is None:
            tasks = repository.create_task_group(
                payload.task_text,
                payload.deadline,
                payload.group_id,
                payload.assigned_to,
                payload.assigned_by,
            )
            group_task_id = tasks[0].group_task_id if tasks else None
        else:
            tasks = repository.add_executors_to_group(
                payload.group_task_id,
                payload.assigned_to,
                payload.assigned_by,
            )
            group_task_id = payload.group_task_id
        return {"success": True, "group_task_id": group_task_id, "tasks": [t.model_dump() for t in tasks]}
    except ValueError as exc:
        logging.exception("Invalid request for creating or adding tasks")
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logging.exception("Failed to process task creation or executor addition")
        raise


@app.post("/api/tasks/executors")
def add_executors(payload: TaskAddExecutors) -> dict:
    try:
        tasks = repository.add_executors_to_group(
            payload.group_task_id, payload.assigned_to, payload.assigned_by
        )
        return {"success": True, "group_task_id": payload.group_task_id, "tasks": [t.model_dump() for t in tasks]}
    except ValueError as exc:
        logging.exception("Group not found while adding executors")
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logging.exception("Failed to add executors via endpoint")
        raise


class ExecutorsReplacePayload(TaskAddExecutors):
    pass


@app.put("/api/tasks/{group_task_id}/executors")
def replace_executors(group_task_id: int, payload: ExecutorsReplacePayload) -> dict:
    try:
        if group_task_id != payload.group_task_id:
            raise ValueError("group_task_id mismatch")
        tasks = repository.replace_executors(payload)
        return {"success": True, "group_task_id": group_task_id, "tasks": [t.model_dump() for t in tasks]}
    except ValueError as exc:
        logging.exception("Failed to replace executors for group %s", group_task_id)
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logging.exception("Unexpected error replacing executors")
        raise


@app.put("/api/tasks/{task_id}")
def update_task(
    task_id: int,
    payload: Union[TaskStatusUpdate, GroupOperationRequest] = Body(...),
) -> dict:
    try:
        if isinstance(payload, GroupOperationRequest) and payload.group_operation:
            task = repository.get_task_by_id(task_id)
            if task is None:
                raise ValueError(f"Task {task_id} does not exist")
            repository.update_group(task.group_task_id, payload)
            return {"success": True, "group_task_id": task.group_task_id}
        updated_task = repository.update_task_status(task_id, payload.status)
        return {"success": True, "task": updated_task}
    except ValueError as exc:
        logging.exception("Task or group not found for update")
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logging.exception("Failed to update task or group")
        raise


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int) -> dict:
    try:
        remaining = repository.delete_task(task_id)
        return {"success": True, "remaining_in_group": remaining}
    except ValueError as exc:
        logging.exception("Task not found for deletion")
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logging.exception("Failed to delete task")
        raise


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.web_api:app", host="0.0.0.0", port=8000, reload=True)
