from sqlalchemy import Column, Integer, String, DateTime, JSON, func
# JSONB is PostgreSQL-specific. Using generic JSON for broader compatibility (including SQLite).
from .db import Base

class Task(Base):
    __tablename__ = 'tasks'

    id = Column(Integer, primary_key=True, index=True)
    description = Column(String, nullable=False)
    status = Column(String, default='pending')


class TaskManagerVersion(Base):
    __tablename__ = 'task_manager_versions'

    id = Column(Integer, primary_key=True, index=True)
    version_number = Column(Integer, nullable=False, unique=True, index=True) # Or generate sequentially
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    snapshot_data = Column(JSON, nullable=False) # Stores a list of task-like objects

