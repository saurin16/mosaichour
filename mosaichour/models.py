from pydantic import BaseModel, Field


class PlanRequest(BaseModel):
    artist: str = Field(min_length=2, max_length=100)
    movie: str = Field(min_length=2, max_length=100)
    group_size: int = Field(default=12, ge=2, le=100)
    minutes: int = Field(default=45, ge=20, le=90)
    budget: int = Field(default=30, ge=0, le=500)
    access_need: str = Field(default="seated", pattern="^(seated|hearing|vision|quiet)$")


class ProgramDraft(BaseModel):
    selected_name: str
    title: str
    why_it_fits: str
    opening: str
    steps: list[str]
    closing: str
    host_prompt: str


class DraftBatch(BaseModel):
    programs: list[ProgramDraft]
