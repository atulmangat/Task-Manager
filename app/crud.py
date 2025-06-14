from sqlalchemy.orm import Session
from sqlalchemy import func, desc, delete as sqlalchemy_delete
from . import models, schemas
from typing import List, Optional, Dict, Any

STATUSES = {"pending", "inprogress", "done"}

# --- TaskManagerVersion CRUD --- (Moved up for dependency)

def get_next_version_number(db: Session) -> int:
    """Gets the next available version number."""
    latest_version = db.query(models.TaskManagerVersion).order_by(models.TaskManagerVersion.version_number.desc()).first()
    if latest_version:
        return latest_version.version_number + 1
    return 1 # Start with version 1 if no versions exist

def create_task_manager_version(db: Session, tasks_to_snapshot_data: Optional[List[Dict[str, Any]]] = None) -> models.TaskManagerVersion:
    """Creates a new snapshot version.
    If tasks_to_snapshot_data is provided, it's used directly.
    Otherwise, current live tasks are snapshotted.
    """
    snapshot_data_to_store: List[Dict[str, Any]]

    if tasks_to_snapshot_data is not None:
        # Ensure data is in the correct dict format, not Pydantic models yet
        snapshot_data_to_store = tasks_to_snapshot_data
    else:
        current_live_tasks_orm = db.query(models.Task).all()
        snapshot_items = [
            schemas.TaskSnapshotItem(
                id=task.id,
                description=task.description,
                status=task.status
            ).model_dump() for task in current_live_tasks_orm
        ]
        snapshot_data_to_store = snapshot_items

    next_version_number = get_next_version_number(db)
    
    db_version = models.TaskManagerVersion(
        version_number=next_version_number,
        snapshot_data=snapshot_data_to_store
    )
    db.add(db_version)
    db.commit()
    db.refresh(db_version)
    return db_version

def _update_live_tasks_from_snapshot(db: Session, snapshot_data: List[Dict[str, Any]]):
    """Deletes all current live tasks and replaces them with tasks from the snapshot_data."""
    # Delete all existing tasks
    db.execute(sqlalchemy_delete(models.Task))
    # Add new tasks from snapshot
    for task_data in snapshot_data:
        # Ensure status is valid if coming from an older schema or direct dict manipulation
        status = task_data.get('status', 'pending')
        if status not in STATUSES:
            status = 'pending' # Default to pending if status is invalid
        
        db_task = models.Task(
            id=task_data['id'], 
            description=task_data['description'], 
            status=status
        )
        db.add(db_task)
    db.commit()

def get_task_manager_version(db: Session, version_number: int) -> models.TaskManagerVersion | None:
    return db.query(models.TaskManagerVersion).filter(models.TaskManagerVersion.version_number == version_number).first()

def list_task_manager_versions(db: Session, skip: int = 0, limit: int = 100) -> List[models.TaskManagerVersion]:
    return (
        db.query(models.TaskManagerVersion)
        .order_by(models.TaskManagerVersion.version_number.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

def get_latest_task_manager_version(db: Session) -> models.TaskManagerVersion | None:
    return db.query(models.TaskManagerVersion).order_by(models.TaskManagerVersion.version_number.desc()).first()

# --- Task CRUD --- (Now uses the modified versioning logic)

def create_task(db: Session, task_create_data: schemas.TaskCreate) -> Dict[str, Any]:
    final_snapshot_tasks: List[Dict[str, Any]]

    if task_create_data.base_version_number is not None:
        base_version = get_task_manager_version(db, task_create_data.base_version_number)
        if not base_version:
            raise ValueError(f"Base version {task_create_data.base_version_number} not found.")
        # Operate on a copy of the snapshot data
        current_snapshot_tasks = list(base_version.snapshot_data) # Ensure it's a mutable copy
        
        new_task_id = (max(t['id'] for t in current_snapshot_tasks) + 1) if current_snapshot_tasks else 1
        new_task_data = {
            "id": new_task_id,
            "description": task_create_data.description,
            "status": task_create_data.status
        }
        current_snapshot_tasks.append(new_task_data)
        final_snapshot_tasks = current_snapshot_tasks
        created_task_representation = new_task_data
    else:
        # Standard operation: add to live table first
        db_task = models.Task(description=task_create_data.description, status=task_create_data.status)
        db.add(db_task)
        db.commit()
        db.refresh(db_task)
        # Snapshot will be of the live table
        final_snapshot_tasks = None # Signal create_task_manager_version to use live tasks
        created_task_representation = schemas.TaskRead.from_orm(db_task).model_dump()

    new_version_orm = create_task_manager_version(db, tasks_to_snapshot_data=final_snapshot_tasks)
    if task_create_data.base_version_number is not None:
        _update_live_tasks_from_snapshot(db, new_version_orm.snapshot_data)
    
    return created_task_representation


def list_tasks(db: Session) -> List[models.Task]: # This lists live tasks, usually for internal use now
    return db.query(models.Task).all()


def update_task(db: Session, task_id: int, task_update_data: schemas.TaskUpdate) -> Optional[Dict[str, Any]]:
    updated_task_representation: Optional[Dict[str, Any]] = None

    if task_update_data.base_version_number is not None:
        base_version = get_task_manager_version(db, task_update_data.base_version_number)
        if not base_version:
            raise ValueError(f"Base version {task_update_data.base_version_number} not found.")
        
        current_snapshot_tasks = list(base_version.snapshot_data)
        task_found_in_snapshot = False
        for i, task_dict in enumerate(current_snapshot_tasks):
            if task_dict['id'] == task_id:
                if task_update_data.description is not None:
                    current_snapshot_tasks[i]['description'] = task_update_data.description
                if task_update_data.status is not None and task_update_data.status in STATUSES:
                    current_snapshot_tasks[i]['status'] = task_update_data.status
                updated_task_representation = current_snapshot_tasks[i]
                task_found_in_snapshot = True
                break
        if not task_found_in_snapshot:
            return None # Task not found in the specified historical version's snapshot
        
        final_snapshot_tasks = current_snapshot_tasks
    else:
        db_task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not db_task:
            return None
        if task_update_data.description is not None:
            db_task.description = task_update_data.description
        if task_update_data.status is not None and task_update_data.status in STATUSES:
            db_task.status = task_update_data.status
        db.commit()
        db.refresh(db_task)
        final_snapshot_tasks = None # Signal to snapshot live tasks
        updated_task_representation = schemas.TaskRead.from_orm(db_task).model_dump()

    if updated_task_representation is None: # Should not happen if logic is correct
        return None

    new_version_orm = create_task_manager_version(db, tasks_to_snapshot_data=final_snapshot_tasks)
    if task_update_data.base_version_number is not None:
        _update_live_tasks_from_snapshot(db, new_version_orm.snapshot_data)

    return updated_task_representation


def delete_task(db: Session, task_id: int, base_version_number: Optional[int] = None) -> Optional[Dict[str, Any]]:
    deleted_task_representation: Optional[Dict[str, Any]] = None

    if base_version_number is not None:
        base_version = get_task_manager_version(db, base_version_number)
        if not base_version:
            raise ValueError(f"Base version {base_version_number} not found.")
        
        current_snapshot_tasks = list(base_version.snapshot_data)
        task_found_and_removed = False
        for i, task_dict in enumerate(current_snapshot_tasks):
            if task_dict['id'] == task_id:
                deleted_task_representation = current_snapshot_tasks.pop(i)
                task_found_and_removed = True
                break
        if not task_found_and_removed:
            return None # Task not found in snapshot
        
        final_snapshot_tasks = current_snapshot_tasks
    else:
        db_task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not db_task:
            return None
        deleted_task_representation = schemas.TaskRead.from_orm(db_task).model_dump()
        db.delete(db_task)
        db.commit()
        final_snapshot_tasks = None # Signal to snapshot live tasks

    if deleted_task_representation is None: # Should not happen
        return None

    new_version_orm = create_task_manager_version(db, tasks_to_snapshot_data=final_snapshot_tasks)
    if base_version_number is not None:
        _update_live_tasks_from_snapshot(db, new_version_orm.snapshot_data)

    return deleted_task_representation

