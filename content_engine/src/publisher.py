"""
Publisher Module - Metricool Content Calendar Integration.

Handles media upload, content scheduling, and cross-platform
publishing via Metricool API.
"""

import base64
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import PlatformConstraints, get_settings
from .logger import get_logger
from .models import (
    GeneratedContent,
    GeneratedImage,
    Platform,
    PublishRequest,
    PublishResult,
)

logger = get_logger(__name__)


class MetricoolPublisher:
    """
    Publisher for scheduling content via Metricool API.

    Handles media upload, content formatting, and calendar injection
    for automated cross-platform posting.
    """

    def __init__(self) -> None:
        """Initialize the Metricool publisher."""
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
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an async HTTP request to Metricool API."""
        url = f"{self.base_url}/{endpoint}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            if files:
                headers = {k: v for k, v in self.headers.items() if k != "Content-Type"}
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    files=files,
                    data=json_data,
                )
            else:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    params=params,
                    json=json_data,
                )

            response.raise_for_status()

            if response.content:
                return response.json()
            return {"success": True}

    async def upload_media(
        self,
        image: GeneratedImage,
        platform: Platform,
    ) -> str | None:
        """
        Upload media to Metricool for scheduling.

        Args:
            image: Generated image to upload
            platform: Target platform

        Returns:
            Media ID if successful, None otherwise
        """
        logger.info(f"Uploading media for {platform.value}")

        if image.local_path:
            file_path = Path(image.local_path)
            if file_path.exists():
                image_data = file_path.read_bytes()
                image_base64 = base64.b64encode(image_data).decode()
            else:
                logger.warning(f"Local file not found: {image.local_path}")
                image_base64 = None
        else:
            async with httpx.AsyncClient() as client:
                response = await client.get(image.url)
                response.raise_for_status()
                image_base64 = base64.b64encode(response.content).decode()

        if not image_base64:
            logger.error("Failed to prepare image for upload")
            return None

        payload = {
            "userId": self.settings.metricool_user_id,
            "platform": platform.value,
            "mediaType": "image",
            "mediaData": image_base64,
            "width": image.width,
            "height": image.height,
        }

        try:
            result = await self._make_request("POST", "media/upload", json_data=payload)
            media_id = result.get("mediaId")
            logger.info(f"Media uploaded successfully: {media_id}")
            return media_id
        except Exception as e:
            logger.error(f"Media upload failed: {e}")
            return None

    def _format_content_for_platform(
        self,
        content: GeneratedContent,
    ) -> dict[str, Any]:
        """Format content according to platform requirements."""
        constraints = PlatformConstraints.get(content.platform.value)

        text = content.text.strip()

        if content.hashtags:
            hashtags_str = " ".join(content.hashtags)
            if content.platform == Platform.INSTAGRAM:
                text = f"{text}\n\n.\n.\n.\n{hashtags_str}"
            elif content.platform == Platform.PINTEREST:
                text = f"{text} {hashtags_str}"
            elif content.platform == Platform.TELEGRAM:
                text = f"{text}\n\n{hashtags_str}"

        max_length = constraints.get("max_caption_length", 2200)
        if len(text) > max_length:
            text = text[: max_length - 3] + "..."
            logger.warning(f"Content truncated to {max_length} characters")

        return {
            "text": text,
            "originalLength": len(content.text),
            "finalLength": len(text),
            "hashtagCount": len(content.hashtags),
        }

    def _calculate_optimal_schedule_time(
        self,
        platform: Platform,
        preferred_time: datetime | None = None,
    ) -> datetime:
        """Calculate optimal scheduling time based on platform and preferences."""
        if preferred_time and preferred_time > datetime.utcnow():
            return preferred_time

        default_times = {
            Platform.INSTAGRAM: (9, 12, 17, 20),
            Platform.PINTEREST: (14, 20, 21),
            Platform.TELEGRAM: (8, 12, 18, 21),
        }

        now = datetime.utcnow()
        hours = default_times.get(platform, (12,))

        for hour in hours:
            candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if candidate > now + timedelta(hours=1):
                return candidate

        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=hours[0], minute=0, second=0, microsecond=0)

    async def schedule_post(
        self,
        request: PublishRequest,
    ) -> PublishResult:
        """
        Schedule a post via Metricool.

        Args:
            request: Publish request containing content and image

        Returns:
            PublishResult with scheduling outcome
        """
        content = request.content
        image = request.image
        platform = content.platform

        logger.info(f"Scheduling post for {platform.value}")

        media_id = await self.upload_media(image, platform)
        if not media_id:
            return PublishResult(
                success=False,
                platform=platform,
                error_message="Failed to upload media",
            )

        formatted = self._format_content_for_platform(content)

        schedule_time = self._calculate_optimal_schedule_time(
            platform, request.schedule_time
        )

        payload = {
            "userId": self.settings.metricool_user_id,
            "platform": platform.value,
            "text": formatted["text"],
            "mediaIds": [media_id],
            "scheduledTime": schedule_time.isoformat(),
            "autoPublish": request.auto_publish,
            "contentType": content.content_format.value,
        }

        try:
            result = await self._make_request("POST", "posts/schedule", json_data=payload)

            post_id = result.get("postId")
            logger.info(
                f"Post scheduled successfully: {post_id} "
                f"for {schedule_time.isoformat()}"
            )

            return PublishResult(
                success=True,
                platform=platform,
                post_id=post_id,
                scheduled_time=schedule_time,
                metricool_response=result,
            )

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            logger.error(f"Scheduling failed: {error_msg}")
            return PublishResult(
                success=False,
                platform=platform,
                error_message=error_msg,
            )
        except Exception as e:
            logger.error(f"Scheduling failed: {e}")
            return PublishResult(
                success=False,
                platform=platform,
                error_message=str(e),
            )

    async def schedule_cross_platform(
        self,
        contents: list[GeneratedContent],
        images: list[GeneratedImage],
        schedule_time: datetime | None = None,
        stagger_minutes: int = 30,
    ) -> list[PublishResult]:
        """
        Schedule content across multiple platforms with staggered timing.

        Args:
            contents: List of platform-specific content
            images: List of corresponding images
            schedule_time: Base schedule time (optional)
            stagger_minutes: Minutes between platform posts

        Returns:
            List of publish results
        """
        logger.info(f"Cross-platform scheduling for {len(contents)} platforms")

        if len(images) < len(contents):
            image = images[0] if images else None
            images = [image] * len(contents) if image else []

        if not images:
            return [
                PublishResult(
                    success=False,
                    platform=c.platform,
                    error_message="No images provided",
                )
                for c in contents
            ]

        results: list[PublishResult] = []
        current_time = schedule_time or datetime.utcnow() + timedelta(hours=1)

        for i, (content, image) in enumerate(zip(contents, images)):
            staggered_time = current_time + timedelta(minutes=stagger_minutes * i)

            request = PublishRequest(
                content=content,
                image=image,
                schedule_time=staggered_time,
                auto_publish=self.settings.auto_schedule,
            )

            result = await self.schedule_post(request)
            results.append(result)

        successful = sum(1 for r in results if r.success)
        logger.info(f"Cross-platform scheduling complete: {successful}/{len(results)} successful")

        return results

    async def get_scheduled_posts(
        self,
        platform: Platform | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve scheduled posts from Metricool calendar."""
        params: dict[str, Any] = {
            "userId": self.settings.metricool_user_id,
        }

        if platform:
            params["platform"] = platform.value
        if start_date:
            params["startDate"] = start_date.strftime("%Y-%m-%d")
        if end_date:
            params["endDate"] = end_date.strftime("%Y-%m-%d")

        result = await self._make_request("GET", "posts/scheduled", params=params)
        return result.get("posts", [])

    async def cancel_scheduled_post(self, post_id: str) -> bool:
        """Cancel a scheduled post."""
        try:
            await self._make_request(
                "DELETE",
                f"posts/{post_id}",
                params={"userId": self.settings.metricool_user_id},
            )
            logger.info(f"Canceled scheduled post: {post_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel post {post_id}: {e}")
            return False

    async def update_scheduled_post(
        self,
        post_id: str,
        text: str | None = None,
        schedule_time: datetime | None = None,
    ) -> bool:
        """Update a scheduled post."""
        payload: dict[str, Any] = {
            "userId": self.settings.metricool_user_id,
        }

        if text:
            payload["text"] = text
        if schedule_time:
            payload["scheduledTime"] = schedule_time.isoformat()

        try:
            await self._make_request("PATCH", f"posts/{post_id}", json_data=payload)
            logger.info(f"Updated scheduled post: {post_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update post {post_id}: {e}")
            return False
