"""Pydantic schemas for workflow endpoints."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class NodePosition(BaseModel):
    """Position of a node in the canvas."""

    x: float
    y: float


class WorkflowNode(BaseModel):
    """A node in the workflow."""

    id: str
    type: str
    position: NodePosition
    data: dict[str, Any] = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    """An edge connecting two nodes."""

    id: str
    source: str
    target: str
    sourceHandle: str | None = None
    targetHandle: str | None = None


class WorkflowViewport(BaseModel):
    """Viewport state of the canvas."""

    x: float = 0
    y: float = 0
    zoom: float = 1


class WorkflowCreate(BaseModel):
    """Schema for creating a workflow."""

    name: str = Field(..., max_length=255)
    description: str | None = None
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    viewport: WorkflowViewport = Field(default_factory=WorkflowViewport)
    trigger_type: str | None = Field(None, max_length=50)
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class WorkflowUpdate(BaseModel):
    """Schema for updating a workflow."""

    name: str | None = Field(None, max_length=255)
    description: str | None = None
    nodes: list[WorkflowNode] | None = None
    edges: list[WorkflowEdge] | None = None
    viewport: WorkflowViewport | None = None
    trigger_type: str | None = None
    trigger_config: dict[str, Any] | None = None
    is_active: bool | None = None


class WorkflowRead(BaseModel):
    """Schema for reading a workflow."""

    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]
    viewport: WorkflowViewport
    is_active: bool
    trigger_type: str | None
    trigger_config: dict[str, Any]
    run_count: int
    last_run_at: datetime | None
    avg_duration_ms: int | None
    created_by: UUID | None
    updated_by: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowSummary(BaseModel):
    """Brief workflow info for lists."""

    id: UUID
    name: str
    description: str | None
    is_active: bool
    trigger_type: str | None
    run_count: int
    last_run_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class NodeResult(BaseModel):
    """Result of a single node execution."""

    node_id: str
    status: str  # completed, failed, skipped
    output: dict[str, Any] | None = None
    duration_ms: int | None = None
    completed_at: datetime | None = None
    error: str | None = None


class WorkflowRunCreate(BaseModel):
    """Schema for starting a workflow run."""

    trigger_data: dict[str, Any] = Field(default_factory=dict)
    asset_id: UUID | None = None


class WorkflowRunRead(BaseModel):
    """Schema for reading a workflow run."""

    id: UUID
    workflow_id: UUID
    tenant_id: UUID
    trigger_data: dict[str, Any]
    asset_id: UUID | None
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    current_node_id: str | None
    nodes_completed: list[NodeResult]
    error_message: str | None
    error_node_id: str | None
    error_details: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkflowRunSummary(BaseModel):
    """Brief run info for lists."""

    id: UUID
    workflow_id: UUID
    status: str
    duration_ms: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


# Node type definitions for frontend
NODE_TYPES = {
    "triggers": [
        {"type": "trigger_upload", "label": "Novo Upload", "icon": "upload"},
        {"type": "trigger_schedule", "label": "Agendamento", "icon": "clock"},
        {"type": "trigger_webhook", "label": "Webhook Externo", "icon": "webhook"},
        {"type": "trigger_manual", "label": "Manual", "icon": "play"},
    ],
    "processing": [
        {"type": "process_transcribe", "label": "Transcrever (Whisper)", "icon": "mic"},
        {"type": "process_face_detect", "label": "Detectar Faces", "icon": "user"},
        {"type": "process_face_identify", "label": "Identificar Pessoas", "icon": "users"},
        {"type": "process_describe_scene", "label": "Descrever Cenas", "icon": "eye"},
        {"type": "process_extract_keywords", "label": "Extrair Keywords", "icon": "tag"},
        {"type": "process_generate_proxy", "label": "Gerar Proxy", "icon": "video"},
        {"type": "process_generate_thumbnail", "label": "Gerar Thumbnail", "icon": "image"},
    ],
    "logic": [
        {"type": "logic_condition", "label": "Condição (If/Else)", "icon": "git-branch"},
        {"type": "logic_switch", "label": "Switch", "icon": "list"},
        {"type": "logic_delay", "label": "Aguardar", "icon": "clock"},
        {"type": "logic_loop", "label": "Loop (Para Cada)", "icon": "repeat"},
    ],
    "actions": [
        {"type": "action_add_keyword", "label": "Adicionar Keyword", "icon": "tag"},
        {"type": "action_add_to_collection", "label": "Adicionar à Coleção", "icon": "folder-plus"},
        {"type": "action_update_status", "label": "Atualizar Status", "icon": "check"},
        {"type": "action_notify", "label": "Notificar", "icon": "bell"},
        {"type": "action_webhook", "label": "Chamar Webhook", "icon": "send"},
        {"type": "action_export", "label": "Exportar", "icon": "download"},
    ],
    "integrations": [
        {"type": "integration_slack", "label": "Slack", "icon": "slack"},
        {"type": "integration_email", "label": "Email", "icon": "mail"},
        {"type": "integration_s3", "label": "S3/Storage", "icon": "database"},
        {"type": "integration_api", "label": "API Externa", "icon": "globe"},
    ],
}
