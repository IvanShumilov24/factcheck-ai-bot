from pydantic import BaseModel, Field


class EvidenceCoverage(BaseModel):
    """Completeness of the retrieved evidence, never a truth probability."""

    level: str
    direct_count: int = Field(ge=0)
    indirect_count: int = Field(ge=0)
    not_relevant_count: int = Field(ge=0)
    background_count: int = Field(ge=0)
    supporting_count: int = Field(ge=0)
    contradicting_count: int = Field(ge=0)
    independent_source_count: int = Field(ge=0)
    uncovered_components: list[str] = Field(default_factory=list)
    scope_mismatch: bool = False
