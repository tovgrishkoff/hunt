"""
Analytics Engine - Metricool API Integration.

Fetches cross-platform metrics and analyzes top-performing content
to provide insights for content generation.
"""

import json
from datetime import datetime, timedelta
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import get_settings
from .logger import get_logger
from .models import AnalyticsReport, ContentFormat, Platform, PostMetrics

logger = get_logger(__name__)


class MetricoolClient:
    """Async client for Metricool API integration."""

    def __init__(self) -> None:
        """Initialize the Metricool client."""
        self.settings = get_settings()
        self.base_url = self.settings.metricool_base_url
        self.headers = {
            "Authorization": f"Bearer {self.settings.metricool_api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        before_sleep=lambda retry_state: logger.warning(
            f"Retrying Metricool API call, attempt {retry_state.attempt_number}"
        ),
    )
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an async HTTP request to Metricool API."""
        url = f"{self.base_url}/{endpoint}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=method,
                url=url,
                headers=self.headers,
                params=params,
                json=json_data,
            )
            response.raise_for_status()
            return response.json()

    async def get_account_metrics(
        self,
        platform: Platform,
        start_date: datetime,
        end_date: datetime,
    ) -> dict[str, Any]:
        """Fetch account-level metrics for a specific platform."""
        logger.info(f"Fetching {platform.value} metrics from {start_date} to {end_date}")

        params = {
            "userId": self.settings.metricool_user_id,
            "platform": platform.value,
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d"),
        }

        return await self._make_request("GET", "analytics/account", params=params)

    async def get_posts_metrics(
        self,
        platform: Platform,
        start_date: datetime,
        end_date: datetime,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch individual post metrics for a specific platform."""
        logger.info(f"Fetching {platform.value} posts metrics, limit={limit}")

        params = {
            "userId": self.settings.metricool_user_id,
            "platform": platform.value,
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d"),
            "limit": limit,
            "orderBy": "engagement",
            "orderDirection": "desc",
        }

        response = await self._make_request("GET", "analytics/posts", params=params)
        return response.get("posts", [])

    async def get_best_posting_times(self, platform: Platform) -> list[dict[str, Any]]:
        """Fetch optimal posting times for a platform."""
        logger.info(f"Fetching best posting times for {platform.value}")

        params = {
            "userId": self.settings.metricool_user_id,
            "platform": platform.value,
        }

        response = await self._make_request("GET", "analytics/best-times", params=params)
        return response.get("bestTimes", [])


class AnalyticsEngine:
    """Engine for analyzing content performance across platforms."""

    def __init__(self) -> None:
        """Initialize the analytics engine."""
        self.client = MetricoolClient()
        self.settings = get_settings()

    def _parse_post_metrics(
        self, raw_post: dict[str, Any], platform: Platform
    ) -> PostMetrics:
        """Parse raw API response into PostMetrics model."""
        impressions = raw_post.get("impressions", 0)
        engagement = raw_post.get("engagement", 0)
        engagement_rate = (engagement / impressions * 100) if impressions > 0 else 0.0

        content_type_map = {
            "image": ContentFormat.IMAGE,
            "carousel": ContentFormat.CAROUSEL,
            "video": ContentFormat.VIDEO,
            "story": ContentFormat.STORY,
            "reel": ContentFormat.REEL,
        }

        return PostMetrics(
            post_id=str(raw_post.get("id", "")),
            platform=platform,
            published_at=datetime.fromisoformat(
                raw_post.get("publishedAt", datetime.utcnow().isoformat())
            ),
            impressions=impressions,
            engagement_rate=round(engagement_rate, 2),
            likes=raw_post.get("likes", 0),
            comments=raw_post.get("comments", 0),
            shares=raw_post.get("shares", 0),
            saves=raw_post.get("saves", 0),
            reach=raw_post.get("reach", 0),
            content_type=content_type_map.get(
                raw_post.get("type", "image"), ContentFormat.IMAGE
            ),
            caption=raw_post.get("caption"),
            hashtags=raw_post.get("hashtags", []),
        )

    def _analyze_content_angles(self, posts: list[PostMetrics]) -> list[str]:
        """Extract successful content angles from top posts."""
        angles = []

        keyword_categories = {
            "educational": ["how to", "tips", "guide", "learn", "tutorial", "secret"],
            "inspirational": ["motivation", "inspire", "dream", "success", "mindset"],
            "behind-the-scenes": ["behind", "process", "making", "day in", "routine"],
            "storytelling": ["story", "journey", "experience", "transformation"],
            "actionable": ["step", "strategy", "method", "framework", "system"],
            "personal": ["my", "personal", "honest", "truth", "real"],
        }

        angle_scores: dict[str, float] = {}

        for post in posts:
            if not post.caption:
                continue

            caption_lower = post.caption.lower()

            for angle, keywords in keyword_categories.items():
                if any(kw in caption_lower for kw in keywords):
                    if angle not in angle_scores:
                        angle_scores[angle] = 0
                    angle_scores[angle] += post.engagement_rate

        sorted_angles = sorted(angle_scores.items(), key=lambda x: x[1], reverse=True)
        angles = [angle for angle, _ in sorted_angles[:5]]

        if not angles:
            angles = ["general", "informative"]

        logger.info(f"Identified top content angles: {angles}")
        return angles

    def _analyze_formats(self, posts: list[PostMetrics]) -> list[str]:
        """Analyze which content formats perform best."""
        format_performance: dict[str, list[float]] = {}

        for post in posts:
            format_name = post.content_type.value
            if format_name not in format_performance:
                format_performance[format_name] = []
            format_performance[format_name].append(post.engagement_rate)

        format_avg = {
            fmt: sum(rates) / len(rates) for fmt, rates in format_performance.items()
        }

        sorted_formats = sorted(format_avg.items(), key=lambda x: x[1], reverse=True)
        best_formats = [fmt for fmt, _ in sorted_formats[:3]]

        logger.info(f"Best performing formats: {best_formats}")
        return best_formats

    def _format_posting_times(
        self, times_data: list[dict[str, Any]]
    ) -> list[str]:
        """Format best posting times into readable strings."""
        formatted = []
        for time_slot in times_data[:5]:
            day = time_slot.get("day", "")
            hour = time_slot.get("hour", 0)
            formatted.append(f"{day} at {hour:02d}:00")
        return formatted

    async def generate_report(
        self,
        platforms: list[Platform] | None = None,
        lookback_days: int | None = None,
    ) -> AnalyticsReport:
        """Generate comprehensive analytics report."""
        if platforms is None:
            platforms = [Platform(p) for p in self.settings.default_platforms]

        if lookback_days is None:
            lookback_days = self.settings.analytics_lookback_days

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=lookback_days)

        logger.info(
            f"Generating analytics report for {[p.value for p in platforms]} "
            f"from {start_date.date()} to {end_date.date()}"
        )

        all_posts: list[PostMetrics] = []
        platform_breakdown: dict[str, dict[str, Any]] = {}
        all_posting_times: list[str] = []

        for platform in platforms:
            try:
                raw_posts = await self.client.get_posts_metrics(
                    platform=platform,
                    start_date=start_date,
                    end_date=end_date,
                    limit=self.settings.top_posts_count * 2,
                )

                posts = [self._parse_post_metrics(p, platform) for p in raw_posts]
                all_posts.extend(posts)

                if posts:
                    avg_engagement = sum(p.engagement_rate for p in posts) / len(posts)
                    total_reach = sum(p.reach for p in posts)
                    platform_breakdown[platform.value] = {
                        "total_posts": len(posts),
                        "avg_engagement_rate": round(avg_engagement, 2),
                        "total_reach": total_reach,
                        "top_post_id": posts[0].post_id if posts else None,
                    }

                posting_times = await self.client.get_best_posting_times(platform)
                all_posting_times.extend(
                    self._format_posting_times(posting_times)
                )

            except Exception as e:
                logger.error(f"Error fetching {platform.value} data: {e}")
                continue

        all_posts.sort(key=lambda x: x.engagement_rate, reverse=True)
        top_posts = all_posts[: self.settings.top_posts_count]

        avg_engagement = (
            sum(p.engagement_rate for p in top_posts) / len(top_posts)
            if top_posts
            else 0.0
        )

        best_angles = self._analyze_content_angles(top_posts)
        best_formats = self._analyze_formats(top_posts)

        report = AnalyticsReport(
            period_start=start_date,
            period_end=end_date,
            total_posts=len(all_posts),
            avg_engagement_rate=round(avg_engagement, 2),
            top_performing_posts=top_posts,
            best_content_angles=best_angles,
            best_formats=best_formats,
            best_posting_times=list(set(all_posting_times))[:5],
            platform_breakdown=platform_breakdown,
        )

        logger.info(
            f"Analytics report generated: {report.total_posts} posts analyzed, "
            f"avg engagement: {report.avg_engagement_rate}%"
        )

        return report

    def export_report_json(self, report: AnalyticsReport) -> str:
        """Export analytics report as formatted JSON."""
        return report.model_dump_json(indent=2)

    def get_insights_summary(self, report: AnalyticsReport) -> str:
        """Generate a human-readable insights summary for LLM context."""
        summary_parts = [
            f"## Content Performance Analysis ({report.period_start.date()} to {report.period_end.date()})",
            "",
            f"### Overview",
            f"- Total posts analyzed: {report.total_posts}",
            f"- Average engagement rate: {report.avg_engagement_rate}%",
            "",
            f"### Top Performing Content Angles",
        ]

        for angle in report.best_content_angles:
            summary_parts.append(f"- {angle.title()}")

        summary_parts.extend(
            [
                "",
                "### Best Performing Formats",
            ]
        )

        for fmt in report.best_formats:
            summary_parts.append(f"- {fmt.title()}")

        if report.best_posting_times:
            summary_parts.extend(
                [
                    "",
                    "### Optimal Posting Times",
                ]
            )
            for time in report.best_posting_times:
                summary_parts.append(f"- {time}")

        summary_parts.extend(
            [
                "",
                "### Top Performing Posts (for reference)",
            ]
        )

        for i, post in enumerate(report.top_performing_posts[:5], 1):
            caption_preview = (
                post.caption[:100] + "..." if post.caption and len(post.caption) > 100 else post.caption or "N/A"
            )
            summary_parts.append(
                f"{i}. [{post.platform.value}] Engagement: {post.engagement_rate}% | "
                f"Type: {post.content_type.value} | Caption: {caption_preview}"
            )

        return "\n".join(summary_parts)
