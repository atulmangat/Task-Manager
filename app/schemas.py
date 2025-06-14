from pydantic import BaseModel
from typing import Literal, Optional, List
from datetime import datetime

class TaskCreate(BaseModel):
    description: str
    status: str = 'pending'
    base_version_number: Optional[int] = None

class TaskUpdate(BaseModel):
    description: str | None = None
    status: str | None = None
    base_version_number: Optional[int] = None

class TaskRead(BaseModel):
    id: int
    description: str
    status: str

    class Config:
        from_attributes = True # Updated from orm_mode for Pydantic v2


class VoiceCommandRequest(BaseModel):
    text: str
    model: Optional[str] = None # Keep existing model field
    current_tasks: Optional[List[dict]] = None # Keep existing current_tasks field
    base_version_number: Optional[int] = None

class LLMTaskInstruction(BaseModel):
    action: Literal["create_task", "update_task", "delete_task", "list_tasks", "no_action", "clarify_or_refuse"]
    task_id: Optional[int] = None
    description: Optional[str] = None
    status: Optional[Literal['pending', 'inprogress', 'done']] = None
    query: Optional[str] = None
    response_message: Optional[str] = None # For no_action and clarify_or_refuse


class LLMResponse(BaseModel):
    action: str
    task: Optional[TaskRead] = None
    tasks: Optional[List[TaskRead]] = None
    deleted_task_id: Optional[int] = None
    message: Optional[str] = None


class TranscriptionResponse(BaseModel):
    text: str
    model_name: str

# --- Task Versioning Schemas ---

class TaskSnapshotItem(BaseModel):
    """Represents a task as stored within a version snapshot."""
    id: int # The original task ID
    description: str
    status: Literal['pending', 'inprogress', 'done']

    class Config:
        from_attributes = True

class TaskManagerVersionBase(BaseModel):
    version_number: int
    created_at: datetime

class TaskManagerVersionCreate(TaskManagerVersionBase):
    snapshot_data: List[TaskSnapshotItem]

class TaskManagerVersionRead(TaskManagerVersionBase):
    id: int
    snapshot_data: List[TaskSnapshotItem]

    class Config:
        from_attributes = True

class TaskManagerVersionInfo(TaskManagerVersionBase):
    """Schema for listing versions without the full snapshot data."""
    id: int

    class Config:
        from_attributes = True

