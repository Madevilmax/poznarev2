from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class TaskGroup(BaseModel):
    group_task_id: int
    task_text: str
    deadline: str
    group_id: str
    created_at: str
    executors: List["Task"] = Field(default_factory=list)


class Task(BaseModel):
    id: int
    group_task_id: int
    assigned_to: str
    assigned_by: str
    status: str
    created_at: str
    completed_at: str
    task_text: Optional[str] = None
    deadline: Optional[str] = None
    group_id: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in {"active", "completed"}:
            raise ValueError("status must be 'active' or 'completed'")
        return value


class TaskCreate(BaseModel):
    task_text: str
    deadline: str
    group_id: str
    assigned_to: List[str]
    assigned_by: str


class TaskAddExecutors(BaseModel):
    group_task_id: int
    assigned_to: List[str]
    assigned_by: str


class TaskGroupUpdate(BaseModel):
    task_text: Optional[str] = None
    deadline: Optional[str] = None
    group_id: Optional[str] = None


class TaskStatusUpdate(BaseModel):
    status: str  # "active" or "completed"

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in {"active", "completed"}:
            raise ValueError("status must be 'active' or 'completed'")
        return value


class User(BaseModel):
    username: str
    full_name: Optional[str] = None
    groups: List[str] = []


class Group(BaseModel):
    id: str
    name: str


class Config(BaseModel):
    task_created: bool = True
    task_completed: bool = True
    task_deleted: bool = True
    overdue_reminder: bool = True


class Stats(BaseModel):
    total_tasks: int
    active_tasks: int
    completed_tasks: int
    overdue_tasks: int
    total_users: int
    total_groups: int
