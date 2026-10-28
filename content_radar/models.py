from datetime import datetime

from pydantic import BaseModel, Field, HttpUrl


class Signal(BaseModel):
    source: str
    title: str
    content: str
    url: HttpUrl
    published_at: datetime
    metadata: dict = Field(default_factory=dict)
    category: str | None = None
    relevance: float = 0.0
    score: float = 0.0
