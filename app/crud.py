from sqlalchemy.orm import Session
from . import models, schemas

STATUSES = {"pending", "inprogress", "done"}

def create_task(db: Session, task: schemas.TaskCreate) -> models.Task:
    db_task = models.Task(description=task.description, status=task.status)
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


def list_tasks(db: Session):
    return db.query(models.Task).all()


def update_task(db: Session, task_id: int, task: schemas.TaskUpdate):
    db_task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not db_task:
        return None
    if task.description is not None:
        db_task.description = task.description
    if task.status is not None and task.status in STATUSES:
        db_task.status = task.status
    db.commit()
    db.refresh(db_task)
    return db_task
