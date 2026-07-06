"""
Centralized configuration module using pydantic-settings.

Loads all environment variables and provides typed configuration
for the entire content engine system.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Anthropic API
    anthropic_api_key: str = Field(..., description="Anthropic API key for Claude")
    anthropic_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Claude model to use for content generation",
    )
    anthropic_max_tokens: int = Field(default=4096, ge=100, le=8192)

    # Metricool API
    metricool_api_token: str = Field(..., description="Metricool API token")
    metricool_user_id: str = Field(..., description="Metricool user ID")
    metricool_base_url: str = Field(
        default="https://app.metricool.com/api/v2",
        description="Metricool API base URL",
    )

    # Replicate API (for Flux/Stability)
    replicate_api_token: str = Field(..., description="Replicate API token")
    image_model: str = Field(
        default="black-forest-labs/flux-1.1-pro",
        description="Image generation model on Replicate",
    )
    default_image_style: str = Field(
        default="photorealistic, cinematic lighting, professional photography, 8k quality",
        description="Default style suffix for image prompts",
    )

    # Paths
    chromadb_path: Path = Field(
        default=Path("./data/chromadb"),
        description="Path to ChromaDB storage",
    )
    knowledge_dir: Path = Field(
        default=Path("./knowledge"),
        description="Directory containing knowledge base files",
    )
    log_file: Path = Field(
        default=Path("./logs/content_engine.log"),
        description="Log file path",
    )

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO"
    )

    # Content settings
    default_platforms: list[str] = Field(
        default=["instagram", "pinterest", "telegram"],
        description="Default platforms for content distribution",
    )
    content_language: str = Field(default="en", description="Content language code")
    brand_name: str = Field(default="Brand", description="Brand name for content")

    # Scheduling
    timezone: str = Field(default="UTC", description="Timezone for scheduling")
    auto_schedule: bool = Field(
        default=True, description="Auto-schedule content after generation"
    )

    # API retry settings
    max_retries: int = Field(default=3, ge=1, le=10)
    retry_base_delay: float = Field(default=1.0, ge=0.1, le=10.0)

    # Analytics settings
    analytics_lookback_days: int = Field(
        default=30, ge=7, le=90, description="Days to look back for analytics"
    )
    top_posts_count: int = Field(
        default=10, ge=5, le=50, description="Number of top posts to analyze"
    )

    @field_validator("default_platforms", mode="before")
    @classmethod
    def parse_platforms(cls, v: str | list[str]) -> list[str]:
        """Parse platforms from comma-separated string or list."""
        if isinstance(v, str):
            return [p.strip().lower() for p in v.split(",") if p.strip()]
        return [p.lower() for p in v]

    @field_validator("chromadb_path", "knowledge_dir", "log_file", mode="before")
    @classmethod
    def ensure_path(cls, v: str | Path) -> Path:
        """Ensure value is a Path object."""
        return Path(v) if isinstance(v, str) else v


class PlatformConstraints:
    """Platform-specific content constraints."""

    INSTAGRAM = {
        "max_caption_length": 2200,
        "max_hashtags": 30,
        "image_aspect_ratio": "4:5",
        "image_width": 1080,
        "image_height": 1350,
        "supported_formats": ["jpg", "png"],
    }

    PINTEREST = {
        "max_description_length": 500,
        "max_hashtags": 20,
        "image_aspect_ratio": "2:3",
        "image_width": 1000,
        "image_height": 1500,
        "supported_formats": ["jpg", "png"],
    }

    TELEGRAM = {
        "max_message_length": 4096,
        "max_caption_length": 1024,
        "image_aspect_ratio": "1:1",
        "image_width": 1280,
        "image_height": 1280,
        "supported_formats": ["jpg", "png", "webp"],
    }

    @classmethod
    def get(cls, platform: str) -> dict:
        """Get constraints for a specific platform."""
        platform_map = {
            "instagram": cls.INSTAGRAM,
            "pinterest": cls.PINTEREST,
            "telegram": cls.TELEGRAM,
        }
        return platform_map.get(platform.lower(), cls.INSTAGRAM)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
