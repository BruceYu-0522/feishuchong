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
    model: str = "mock"
    changedFiles: List[str] = Field(default_factory=list)
    workspacePath: Optional[str] = None
    pencilSketchPath: Optional[str] = None
    visualPlan: Optional[dict] = None


class ReviewRecord(BaseModel):
    stageId: str
    stageName: str
    decision: Literal["approve", "reject"]
    reason: str = ""
    createdAt: str


class Pipeline(BaseModel):
    id: str
    requirement: str
    projectPath: Optional[str] = None
    status: Literal["ready", "waiting_review", "completed"]
    currentStageId: str
    stages: List[Stage]
    artifacts: Dict[str, Artifact] = Field(default_factory=dict)
    reviewHistory: List[ReviewRecord] = Field(default_factory=list)


class CreatePipelineRequest(BaseModel):
    requirement: str
    projectPath: Optional[str] = None


class ReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]
    reason: Optional[str] = ""
