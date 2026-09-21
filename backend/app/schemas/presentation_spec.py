from typing import Literal, Union, List, Optional
from pydantic import BaseModel, Field


class Citation(BaseModel):
    document_name: str
    page: Optional[int] = None
    section: Optional[str] = None
    excerpt: Optional[str] = None


class BaseSlideSpec(BaseModel):
    title: str
    citations: List[Citation] = Field(default_factory=list)


class TitleSlideSpec(BaseSlideSpec):
    type: Literal["title"] = "title"
    subtitle: Optional[str] = None


class SectionSlideSpec(BaseSlideSpec):
    type: Literal["section"] = "section"
    subtitle: Optional[str] = None


class BulletSlideSpec(BaseSlideSpec):
    type: Literal["bullet"] = "bullet"
    bullets: List[str]


class TwoColumnSlideSpec(BaseSlideSpec):
    type: Literal["two_column"] = "two_column"
    left_title: str
    left_content: List[str]
    right_title: str
    right_content: List[str]


class TableSlideSpec(BaseSlideSpec):
    type: Literal["table"] = "table"
    columns: List[str]
    rows: List[List[str]]


class ChartSlideSpec(BaseSlideSpec):
    type: Literal["chart"] = "chart"
    chart_type: Literal["bar", "line", "pie"]
    labels: List[str]
    values: List[float]


class QuoteSlideSpec(BaseSlideSpec):
    type: Literal["quote"] = "quote"
    quote: str
    author: Optional[str] = None


class SummarySlideSpec(BaseSlideSpec):
    type: Literal["summary"] = "summary"
    key_takeaways: List[str]


SlideSpec = Union[
    TitleSlideSpec,
    SectionSlideSpec,
    BulletSlideSpec,
    TwoColumnSlideSpec,
    TableSlideSpec,
    ChartSlideSpec,
    QuoteSlideSpec,
    SummarySlideSpec,
]


class PresentationSpec(BaseModel):
    title: str
    subtitle: Optional[str] = None
    slides: List[SlideSpec]
