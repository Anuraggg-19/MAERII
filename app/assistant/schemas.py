from typing import Literal, Optional
from pydantic import BaseModel, Field

Language = Literal["en-IN", "hi-IN", "mr-IN"]

class Context(BaseModel):
    material_id: Optional[int] = Field(default=None, gt=0)
    section: Literal["overview", "categories", "market", "recommendations", "marketing"] = "overview"
    refs: dict[str, str] = Field(default_factory=dict, max_length=5)
    product: Optional[str] = Field(default=None, max_length=200)

class Question(BaseModel):
    language: Language = "en-IN"
    context: Context = Field(default_factory=Context)
    question_id: Optional[str] = Field(default=None, max_length=3)
    text: Optional[str] = Field(default=None, min_length=1, max_length=500)
    term: Optional[str] = Field(default=None, max_length=80)

class AudioRequest(BaseModel):
    answer_id: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]+$")

class Feedback(BaseModel):
    answer_id: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]+$")
    helpful: bool
