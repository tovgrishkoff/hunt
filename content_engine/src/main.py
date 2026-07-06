"""
Content Engine - Main Orchestrator.

Ties together the complete pipeline:
Analyze -> Retrieve Context -> Generate Text & Visual -> Generate Image -> Publish
"""

import asyncio
import time
from datetime import datetime
from typing import Any

from .analytics_engine import AnalyticsEngine
from .config import get_settings
from .content_generator import ContentGenerator
from .image_generator import ImageGenerator
from .knowledge_base import KnowledgeBase, create_sample_knowledge_files
from .logger import get_logger, setup_logging
from .models import (
    ContentRequest,
    GeneratedContent,
    GeneratedImage,
    PipelineResult,
    Platform,
    PublishRequest,
    PublishResult,
)
from .publisher import MetricoolPublisher

logger = get_logger(__name__)


class ContentEngine:
    """
    Autonomous AI Agent for multi-platform content creation.

    Orchestrates the complete pipeline from analytics analysis
    to content scheduling across all configured platforms.
    """

    def __init__(self, auto_init_knowledge: bool = True) -> None:
        """
        Initialize the content engine.

        Args:
            auto_init_knowledge: Whether to auto-ingest knowledge base files
        """
        setup_logging()
        self.settings = get_settings()

        logger.info("Initializing Content Engine...")

        self.analytics = AnalyticsEngine()
        self.knowledge_base = KnowledgeBase()
        self.content_generator = ContentGenerator()
        self.image_generator = ImageGenerator()
        self.publisher = MetricoolPublisher()

        if auto_init_knowledge:
            self._init_knowledge_base()

        logger.info("Content Engine initialized successfully")

    def _init_knowledge_base(self) -> None:
        """Initialize and populate knowledge base if empty."""
        stats = self.knowledge_base.stats()

        if stats["document_count"] == 0:
            logger.info("Knowledge base empty, creating sample files...")
            create_sample_knowledge_files(self.settings.knowledge_dir)
            self.knowledge_base.ingest_directory()

    async def run_pipeline(
        self,
        topic: str,
        platforms: list[Platform] | None = None,
        schedule: bool = True,
        generate_images: bool = True,
    ) -> PipelineResult:
        """
        Execute the complete content creation pipeline.

        Args:
            topic: Content topic/subject
            platforms: Target platforms (defaults to config)
            schedule: Whether to schedule content via Metricool
            generate_images: Whether to generate images

        Returns:
            PipelineResult with all generated content and results
        """
        start_time = time.time()
        errors: list[str] = []

        if platforms is None:
            platforms = [Platform(p) for p in self.settings.default_platforms]

        logger.info(
            f"Starting pipeline | Topic: '{topic}' | "
            f"Platforms: {[p.value for p in platforms]}"
        )

        logger.info("Step 1/5: Fetching analytics...")
        try:
            analytics_report = await self.analytics.generate_report(platforms)
            insights_summary = self.analytics.get_insights_summary(analytics_report)
            logger.info(f"Analytics: {analytics_report.total_posts} posts analyzed")
        except Exception as e:
            logger.error(f"Analytics failed: {e}")
            analytics_report = None
            insights_summary = ""
            errors.append(f"Analytics: {str(e)}")

        logger.info("Step 2/5: Retrieving knowledge context...")
        try:
            brand_context = self.knowledge_base.get_brand_guidelines()
            topic_context = self.knowledge_base.get_topic_context(topic)

            combined_docs = brand_context.documents + topic_context.documents
            combined_sources = brand_context.sources + topic_context.sources

            from .models import KnowledgeContext
            knowledge_context = KnowledgeContext(
                query=f"brand guidelines + {topic}",
                documents=combined_docs,
                sources=combined_sources,
                relevance_scores=brand_context.relevance_scores + topic_context.relevance_scores,
            )

            logger.info(f"Retrieved {len(combined_docs)} knowledge documents")
        except Exception as e:
            logger.error(f"Knowledge retrieval failed: {e}")
            knowledge_context = None
            errors.append(f"Knowledge: {str(e)}")

        logger.info("Step 3/5: Generating content...")
        try:
            content_request = ContentRequest(
                topic=topic,
                platforms=platforms,
            )

            generated_contents = await self.content_generator.generate_content(
                request=content_request,
                knowledge_context=knowledge_context,
                analytics_report=analytics_report,
            )

            logger.info(f"Generated content for {len(generated_contents)} platforms")
        except Exception as e:
            logger.error(f"Content generation failed: {e}")
            generated_contents = []
            errors.append(f"Content generation: {str(e)}")

        generated_images: list[GeneratedImage] = []

        if generate_images and generated_contents:
            logger.info("Step 4/5: Generating images...")
            try:
                for content in generated_contents:
                    refined_prompt = await self.content_generator.refine_visual_prompt(
                        base_prompt=content.visual_prompt,
                        platform=content.platform,
                    )

                    image_request = self.image_generator.create_image_request(
                        prompt=refined_prompt,
                        platform=content.platform,
                    )

                    image = await self.image_generator.generate_image(image_request)
                    generated_images.append(image)

                logger.info(f"Generated {len(generated_images)} images")
            except Exception as e:
                logger.error(f"Image generation failed: {e}")
                errors.append(f"Image generation: {str(e)}")
        else:
            logger.info("Step 4/5: Skipping image generation")

        publish_results: list[PublishResult] = []

        if schedule and generated_contents and generated_images:
            logger.info("Step 5/5: Scheduling content...")
            try:
                publish_results = await self.publisher.schedule_cross_platform(
                    contents=generated_contents,
                    images=generated_images,
                )

                successful = sum(1 for r in publish_results if r.success)
                logger.info(f"Scheduled {successful}/{len(publish_results)} posts")
            except Exception as e:
                logger.error(f"Publishing failed: {e}")
                errors.append(f"Publishing: {str(e)}")
        else:
            logger.info("Step 5/5: Skipping scheduling")

        execution_time = time.time() - start_time

        result = PipelineResult(
            success=len(errors) == 0,
            analytics_report=analytics_report,
            generated_contents=generated_contents,
            generated_images=generated_images,
            publish_results=publish_results,
            errors=errors,
            execution_time_seconds=round(execution_time, 2),
        )

        logger.info(
            f"Pipeline complete | Success: {result.success} | "
            f"Time: {execution_time:.2f}s | Errors: {len(errors)}"
        )

        return result

    async def generate_content_only(
        self,
        topic: str,
        platforms: list[Platform] | None = None,
    ) -> list[GeneratedContent]:
        """Generate content without images or scheduling."""
        if platforms is None:
            platforms = [Platform(p) for p in self.settings.default_platforms]

        brand_context = self.knowledge_base.get_brand_guidelines()
        topic_context = self.knowledge_base.get_topic_context(topic)

        from .models import KnowledgeContext
        knowledge_context = KnowledgeContext(
            query=topic,
            documents=brand_context.documents + topic_context.documents,
            sources=brand_context.sources + topic_context.sources,
            relevance_scores=brand_context.relevance_scores + topic_context.relevance_scores,
        )

        content_request = ContentRequest(topic=topic, platforms=platforms)

        return await self.content_generator.generate_content(
            request=content_request,
            knowledge_context=knowledge_context,
        )

    async def analyze_performance(
        self,
        platforms: list[Platform] | None = None,
    ) -> dict[str, Any]:
        """Run analytics only and return insights."""
        if platforms is None:
            platforms = [Platform(p) for p in self.settings.default_platforms]

        report = await self.analytics.generate_report(platforms)

        return {
            "report": report.model_dump(),
            "summary": self.analytics.get_insights_summary(report),
            "json": self.analytics.export_report_json(report),
        }

    def add_knowledge(
        self,
        text: str,
        source: str = "manual_input",
    ) -> int:
        """Add text to the knowledge base."""
        return self.knowledge_base.ingest_text(text, source)

    def get_knowledge_stats(self) -> dict[str, Any]:
        """Get knowledge base statistics."""
        return self.knowledge_base.stats()


async def main() -> None:
    """Main entry point for CLI execution."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Content Engine - Autonomous AI Content Agent"
    )
    parser.add_argument(
        "topic",
        type=str,
        help="Content topic to generate",
    )
    parser.add_argument(
        "--platforms",
        type=str,
        default="instagram,pinterest,telegram",
        help="Comma-separated platforms",
    )
    parser.add_argument(
        "--no-schedule",
        action="store_true",
        help="Skip scheduling (generate only)",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip image generation",
    )
    parser.add_argument(
        "--analytics-only",
        action="store_true",
        help="Run analytics only",
    )

    args = parser.parse_args()

    engine = ContentEngine()

    if args.analytics_only:
        platforms = [Platform(p.strip()) for p in args.platforms.split(",")]
        result = await engine.analyze_performance(platforms)
        print("\n" + result["summary"])
        return

    platforms = [Platform(p.strip()) for p in args.platforms.split(",")]

    result = await engine.run_pipeline(
        topic=args.topic,
        platforms=platforms,
        schedule=not args.no_schedule,
        generate_images=not args.no_images,
    )

    print("\n" + "=" * 50)
    print("PIPELINE RESULT")
    print("=" * 50)
    print(f"Success: {result.success}")
    print(f"Execution Time: {result.execution_time_seconds}s")
    print(f"Content Generated: {len(result.generated_contents)}")
    print(f"Images Generated: {len(result.generated_images)}")
    print(f"Posts Scheduled: {sum(1 for r in result.publish_results if r.success)}")

    if result.errors:
        print("\nErrors:")
        for error in result.errors:
            print(f"  - {error}")

    print("\nGenerated Content Preview:")
    for content in result.generated_contents:
        print(f"\n[{content.platform.value.upper()}]")
        print(content.text[:200] + "..." if len(content.text) > 200 else content.text)


if __name__ == "__main__":
    asyncio.run(main())
