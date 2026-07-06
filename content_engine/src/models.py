"""
Pydantic models for strict data validation between modules.

Ensures data integrity for analytics, content, images, and publishing.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class Platform(str, Enum):
    """Supported social media platforms."""

    INSTAGRAM = "instagram"
    PINTEREST = "pinterest"
    TELEGRAM = "telegram"


class ContentFormat(str, Enum):
    """Content format types."""

    IMAGE = "image"
    CAROUSEL = "carousel"
    VIDEO = "video"
    STORY = "story"
    REEL = "reel"


class PostMetrics(BaseModel):
    """Metrics for a single post."""

    post_id: str
    platform: Platform
    published_at: datetime
    impressions: int = Field(ge=0)
    engagement_rate: float = Field(ge=0.0, le=100.0)
    likes: int = Field(ge=0)
    comments: int = Field(ge=0)
    shares: int = Field(ge=0)
    saves: int = Field(ge=0)
    reach: int = Field(ge=0)
    content_type: ContentFormat = ContentFormat.IMAGE
    caption: str | None = None
    hashtags: list[str] = Field(default_factory=list)


class AnalyticsReport(BaseModel):
    """Aggregated analytics report."""

    period_start: datetime
    period_end: datetime
    total_posts: int = Field(ge=0)
    avg_engagement_rate: float = Field(ge=0.0)
    top_performing_posts: list[PostMetrics] = Field(default_factory=list)
    best_content_angles: list[str] = Field(default_factory=list)
    best_formats: list[str] = Field(default_factory=list)
    best_posting_times: list[str] = Field(default_factory=list)
    platform_breakdown: dict[str, dict[str, Any]] = Field(default_factory=dict)


class KnowledgeContext(BaseModel):
    """Retrieved context from knowledge base."""

    query: str
    documents: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    relevance_scores: list[float] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def combined_context(self) -> str:
        """Combine all documents into a single context string."""
        return "\n\n---\n\n".join(self.documents)


class ContentRequest(BaseModel):
    """Request for content generation."""

    topic: str = Field(..., min_length=3, max_length=500)
    platforms: list[Platform] = Field(default=[Platform.INSTAGRAM])
    content_format: ContentFormat = ContentFormat.IMAGE
    tone: str = Field(default="professional")
    include_hashtags: bool = True
    include_cta: bool = True
    custom_instructions: str | None = None
    schedule_time: datetime | None = None


class GeneratedContent(BaseModel):
    """Generated content for a single platform."""

    platform: Platform
    text: str = Field(..., min_length=1)
    hashtags: list[str] = Field(default_factory=list)
    cta: str | None = None
    visual_prompt: str = Field(..., min_length=10)
    content_format: ContentFormat = ContentFormat.IMAGE

    @field_validator("hashtags")
    @classmethod
    def validate_hashtags(cls, v: list[str]) -> list[str]:
        """Ensure hashtags start with #."""
        return [tag if tag.startswith("#") else f"#{tag}" for tag in v]

    @model_validator(mode="after")
    def validate_platform_constraints(self) -> "GeneratedContent":
        """Validate content against platform constraints."""
        from .config import PlatformConstraints

        constraints = PlatformConstraints.get(self.platform.value)

        max_len = constraints.get("max_caption_length", 2200)
        if len(self.text) > max_len:
            self.text = self.text[: max_len - 3] + "..."

        max_hashtags = constraints.get("max_hashtags", 30)
        if len(self.hashtags) > max_hashtags:
            self.hashtags = self.hashtags[:max_hashtags]

        return self


class ImageRequest(BaseModel):
    """Request for image generation."""

    prompt: str = Field(..., min_length=10, max_length=2000)
    platform: Platform = Platform.INSTAGRAM
    aspect_ratio: str = Field(default="4:5")
    width: int = Field(default=1080, ge=256, le=4096)
    height: int = Field(default=1350, ge=256, le=4096)
    style: str | None = None
    negative_prompt: str | None = None

    @model_validator(mode="after")
    def set_dimensions_from_platform(self) -> "ImageRequest":
        """Set dimensions based on platform if not explicitly provided."""
        from .config import PlatformConstraints

        constraints = PlatformConstraints.get(self.platform.value)
        if self.width == 1080 and self.height == 1350:
            self.width = constraints["image_width"]
            self.height = constraints["image_height"]
            self.aspect_ratio = constraints["image_aspect_ratio"]
        return self


class GeneratedImage(BaseModel):
    """Generated image result."""

    url: str
    local_path: str | None = None
    width: int
    height: int
    prompt_used: str
    generation_time_seconds: float = Field(ge=0)
    model: str


class PublishRequest(BaseModel):
    """Request to publish content."""

    content: GeneratedContent
    image: GeneratedImage
    schedule_time: datetime | None = None
    auto_publish: bool = False


class PublishResult(BaseModel):
    """Result of publishing operation."""

    success: bool
    platform: Platform
    post_id: str | None = None
    scheduled_time: datetime | None = None
    error_message: str | None = None
    metricool_response: dict[str, Any] = Field(default_factory=dict)


class PipelineResult(BaseModel):
    """Complete pipeline execution result."""

    success: bool
    analytics_report: AnalyticsReport | None = None
    generated_contents: list[GeneratedContent] = Field(default_factory=list)
    generated_images: list[GeneratedImage] = Field(default_factory=list)
    publish_results: list[PublishResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    execution_time_seconds: float = Field(ge=0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
