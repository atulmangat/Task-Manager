from pydantic import BaseModel

class TaskCreate(BaseModel):
    description: str
    status: str = 'pending'

class TaskUpdate(BaseModel):
    description: str | None = None
    status: str | None = None

class TaskRead(BaseModel):
    id: int
    description: str
    status: str

    class Config:
        orm_mode = True
