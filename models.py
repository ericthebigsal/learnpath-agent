from enum import Enum

from pydantic import BaseModel, Field


class ItemType(str, Enum):
    COURSE = "course"
    LEARNING_PATH = "learning_path"
    VIDEO = "video"


class Level(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class Track(str, Enum):
    LLM_FUNDAMENTALS = "LLM Fundamentals"
    RAG = "RAG"
    MULTI_AGENT_SYSTEMS = "Multi-Agent Systems"
    LLM_EVALUATION = "LLM Evaluation & Testing"
    AGENT_TOOLS_SKILLS = "Agent Tools & Skills"
    CONTEXT_ENGINEERING = "Context Engineering"
    LLM_BILLING = "LLM Billing & Cost Models"


class QuizQuestion(BaseModel):
    question: str
    options: list[str]
    correct_index: int


class CourseSection(BaseModel):
    heading: str
    body: str


class CatalogItem(BaseModel):
    id: str
    title: str
    type: ItemType
    level: Level
    track: Track
    duration_minutes: int
    content: str = ""
    sections: list[CourseSection] = Field(default_factory=list)
    quiz: list[QuizQuestion] = Field(default_factory=list)
    certification_eligible: bool = False
    related_item_ids: list[str] = Field(default_factory=list)


class Catalog(BaseModel):
    items: list[CatalogItem]


class PlanStep(BaseModel):
    item_id: str
    rationale: str


class DroppedItem(BaseModel):
    item_id: str
    rationale: str


class PlanResponse(BaseModel):
    steps: list[PlanStep]
    summary: str
    dropped: list[DroppedItem] = Field(default_factory=list)


class PlanDiff(BaseModel):
    kept: list[str]
    added: list[str]
    removed: list[str]
    reordered: bool
