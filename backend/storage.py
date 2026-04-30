from fastapi import HTTPException

from backend.schemas import Pipeline


class InMemoryPipelineStore:
    def __init__(self) -> None:
        self._pipelines: dict[str, Pipeline] = {}

    def save(self, pipeline: Pipeline) -> Pipeline:
        self._pipelines[pipeline.id] = pipeline
        return pipeline

    def get(self, pipeline_id: str) -> Pipeline:
        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            raise HTTPException(status_code=404, detail="Pipeline 不存在")
        return pipeline

    def clear(self) -> None:
        self._pipelines.clear()


store = InMemoryPipelineStore()
