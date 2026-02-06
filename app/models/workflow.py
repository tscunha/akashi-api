"""Workflow models for visual pipeline orchestration."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Workflow(Base):
    """Model for storing workflow definitions (React Flow based)."""

    __tablename__ = "workflows"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Basic info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # React Flow data
    nodes: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )  # [{id, type, position, data}]
    edges: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )  # [{id, source, target}]
    viewport: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=lambda: {"x": 0, "y": 0, "zoom": 1}
    )

    # Configuration
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    trigger_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, index=True
    )  # upload, schedule, webhook, manual
    trigger_config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Stats
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    avg_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Ownership
    created_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    runs: Mapped[list["WorkflowRun"]] = relationship(
        "WorkflowRun",
        back_populates="workflow",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Workflow(id={self.id}, name={self.name})>"


class WorkflowRun(Base):
    """Model for storing workflow execution history."""

    __tablename__ = "workflow_runs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    workflow_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Context
    trigger_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    asset_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True, index=True
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending", index=True
    )  # pending, running, completed, failed, cancelled
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Progress
    current_node_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nodes_completed: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )  # [{node_id, status, output, duration_ms, completed_at}]

    # Error info
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_node_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    # Relationships
    workflow: Mapped[Workflow] = relationship(
        "Workflow",
        back_populates="runs",
        lazy="joined",
    )

    def __repr__(self) -> str:
        return f"<WorkflowRun(id={self.id}, workflow_id={self.workflow_id}, status={self.status})>"

    @property
    def duration_ms(self) -> int | None:
        """Calculate run duration in milliseconds."""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None
