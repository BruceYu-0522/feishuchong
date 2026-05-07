from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SkillInfo(BaseModel):
    id: str
    name: str
    path: str


class Stage(BaseModel):
    id: str
    name: str
    agent: str
    approvalRequired: bool
    skill: SkillInfo


class Artifact(BaseModel):
    stageId: str
    stageName: str
    agent: str
    skill: SkillInfo
    content: str
    createdAt: str
    model: str
    changedFiles: List[str] = Field(default_factory=list)
    workspacePath: Optional[str] = None
    pencilSketchPath: Optional[str] = None
    visualPlan: Optional[dict] = None
    prototypeHtml: Optional[str] = None
    mermaidCode: Optional[str] = None
    mermaidSvg: Optional[str] = None
    prdImageUrl: Optional[str] = None
    # Observability fields
    startedAt: str = ""
    completedAt: str = ""
    latencyMs: int = 0
    promptTokens: int = 0
    completionTokens: int = 0
    totalTokens: int = 0
    reasoningContent: str = ""
    attempt: int = 1


class ReviewRecord(BaseModel):
    stageId: str
    stageName: str
    decision: Literal["approve", "reject"]
    reason: str = ""
    createdAt: str


class Pipeline(BaseModel):
    id: str
    requirement: str
    template: str = "feature"
    projectPath: Optional[str] = None
    status: Literal["ready", "waiting_review", "completed"]
    currentStageId: str
    stages: List[Stage]
    artifacts: Dict[str, Artifact] = Field(default_factory=dict)
    reviewHistory: List[ReviewRecord] = Field(default_factory=list)
    # Observability fields
    createdAt: str = ""
    startedAt: str = ""
    completedAt: str = ""


class CreatePipelineRequest(BaseModel):
    requirement: str
    template: str = "feature"
    projectPath: Optional[str] = None


class ReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]
    reason: Optional[str] = ""


# ── Template models ──

class StageDef(BaseModel):
    id: str
    name: str
    agent: str
    approvalRequired: bool


class PipelineTemplate_(BaseModel):
    id: str
    name: str
    description: str = ""
    stages: List[StageDef] = Field(default_factory=list)
    isBuiltin: bool = False
    createdAt: str = ""
    updatedAt: str = ""


class CreateTemplateRequest(BaseModel):
    id: str
    name: str
    description: str = ""
    stages: List[StageDef] = Field(default_factory=list)


class UpdateTemplateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    stages: Optional[List[StageDef]] = None


# ── Observability models ──

class StageStats(BaseModel):
    stageId: str
    stageName: str
    agent: str
    model: str
    status: str  # "completed" | "failed"
    startedAt: str
    completedAt: str
    latencyMs: int
    promptTokens: int
    completionTokens: int
    totalTokens: int
    attempt: int


class PipelineStats(BaseModel):
    pipelineId: str
    totalLatencyMs: int
    totalPromptTokens: int
    totalCompletionTokens: int
    totalTokens: int
    stages: List[StageStats] = Field(default_factory=list)
    successRate: float = 0.0
