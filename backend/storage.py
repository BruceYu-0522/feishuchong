import json
from pathlib import Path

from fastapi import HTTPException

from backend.schemas import Pipeline

# Store pipelines as JSON files alongside run workspaces
RUNS_DIR = Path("devflow-runs")


class InMemoryPipelineStore:
    def __init__(self) -> None:
        self._pipelines: dict[str, Pipeline] = {}
        self._load_all()

    def _path_for(self, pipeline_id: str) -> Path:
        return RUNS_DIR / pipeline_id / "pipeline.json"

    def _load_all(self) -> None:
        """Restore pipelines from disk on startup."""
        if not RUNS_DIR.exists():
            return
        for run_dir in RUNS_DIR.iterdir():
            if not run_dir.is_dir():
                continue
            f = run_dir / "pipeline.json"
            if f.exists():
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    self._pipelines[data["id"]] = Pipeline(**data)
                except Exception:
                    pass

    def save(self, pipeline: Pipeline) -> Pipeline:
        self._pipelines[pipeline.id] = pipeline
        # Persist to disk
        try:
            p = self._path_for(pipeline.id)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(pipeline.model_dump_json(indent=2), encoding="utf-8")
        except Exception:
            pass
        return pipeline

    def get(self, pipeline_id: str) -> Pipeline:
        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            raise HTTPException(status_code=404, detail="Pipeline 不存在。请确认后端没有重启过，或重新提交需求。")
        return pipeline

    def clear(self) -> None:
        self._pipelines.clear()


store = InMemoryPipelineStore()
