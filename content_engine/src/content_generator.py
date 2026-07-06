"""
Content Generator Module - Claude/Anthropic Integration.

Generates context-aware, platform-optimized content using
analytics insights and knowledge base context.
"""

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
    AnalyticsReport,
    ContentFormat,
    ContentRequest,
    GeneratedContent,
    KnowledgeContext,
    Platform,
)

logger = get_logger(__name__)


class ContentGenerator:
    """
    AI-powered content generator using Claude (Anthropic).

    Produces platform-optimized content grounded in brand guidelines
    and informed by analytics insights.
    """

    def __init__(self) -> None:
        """Initialize the content generator."""
        self.settings = get_settings()
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.headers = {
            "x-api-key": self.settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _build_system_prompt(
        self,
        knowledge_context: KnowledgeContext | None = None,
        analytics_report: AnalyticsReport | None = None,
    ) -> str:
        """Build comprehensive system prompt with all context."""
        prompt_parts = [
            "You are an expert social media content strategist and copywriter.",
            f"Brand: {self.settings.brand_name}",
            f"Content Language: {self.settings.content_language}",
            "",
            "## Your Core Directives:",
            "1. Create engaging, scroll-stopping content that drives action",
            "2. Match the brand voice precisely based on provided guidelines",
            "3. Optimize content for each specific platform's best practices",
            "4. Include strategic hooks that capture attention in first 2 seconds",
            "5. Balance value delivery with engagement optimization",
            "",
        ]

        if knowledge_context and knowledge_context.documents:
            prompt_parts.extend(
                [
                    "## Brand Guidelines & Knowledge Base:",
                    "Use the following context to ensure brand alignment:",
                    "",
                    knowledge_context.combined_context,
                    "",
                ]
            )

        if analytics_report:
            prompt_parts.extend(
                [
                    "## Performance Insights (use these to inform content strategy):",
                    f"- Average engagement rate: {analytics_report.avg_engagement_rate}%",
                    f"- Top performing content angles: {', '.join(analytics_report.best_content_angles)}",
                    f"- Best formats: {', '.join(analytics_report.best_formats)}",
                    "",
                    "Prioritize content angles and formats that have proven to perform well.",
                    "",
                ]
            )

        prompt_parts.extend(
            [
                "## Platform-Specific Requirements:",
                "",
                "### Instagram:",
                f"- Max caption: {PlatformConstraints.INSTAGRAM['max_caption_length']} chars",
                f"- Max hashtags: {PlatformConstraints.INSTAGRAM['max_hashtags']}",
                "- Start with a strong hook (question, bold statement, or story)",
                "- Use line breaks for readability",
                "- End with clear CTA",
                "- Place hashtags at the end or in first comment",
                "",
                "### Pinterest:",
                f"- Max description: {PlatformConstraints.PINTEREST['max_description_length']} chars",
                "- Focus on searchable, keyword-rich descriptions",
                "- Include actionable value proposition",
                "- Use 2-5 relevant hashtags",
                "",
                "### Telegram:",
                f"- Max message: {PlatformConstraints.TELEGRAM['max_message_length']} chars",
                "- Can be more detailed and conversational",
                "- Use formatting: **bold**, _italic_, `code`",
                "- Include emojis for visual breaks",
                "",
                "## Visual Prompt Guidelines:",
                "When creating image prompts, you must be extremely detailed:",
                "- Describe exact composition, lighting, and camera angle",
                "- Specify realistic human features if applicable (avoid AI artifacts)",
                "- Include mood, color palette, and aesthetic style",
                "- Always end with: 'photorealistic, 8k quality, professional photography'",
                "- Specify aspect ratio based on platform requirements",
            ]
        )

        return "\n".join(prompt_parts)

    def _build_user_prompt(
        self, request: ContentRequest, platform: Platform
    ) -> str:
        """Build user prompt for content generation."""
        constraints = PlatformConstraints.get(platform.value)

        prompt_parts = [
            f"Create content for {platform.value.upper()} about: {request.topic}",
            "",
            f"Content Format: {request.content_format.value}",
            f"Tone: {request.tone}",
            f"Image Aspect Ratio: {constraints['image_aspect_ratio']}",
            "",
        ]

        if request.custom_instructions:
            prompt_parts.extend(
                [
                    "Additional Instructions:",
                    request.custom_instructions,
                    "",
                ]
            )

        prompt_parts.extend(
            [
                "Respond in this exact JSON format:",
                "{",
                '  "text": "The complete caption/post text",',
                '  "hashtags": ["hashtag1", "hashtag2", ...],',
                '  "cta": "Call to action phrase",',
                '  "visual_prompt": "Ultra-detailed image generation prompt"',
                "}",
                "",
                "Important:",
                "- The visual_prompt must be 150-300 words, extremely detailed",
                "- Include ONLY the JSON, no additional text",
            ]
        )

        return "\n".join(prompt_parts)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        before_sleep=lambda retry_state: logger.warning(
            f"Retrying Claude API call, attempt {retry_state.attempt_number}"
        ),
    )
    async def _call_claude(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Make async API call to Claude."""
        payload = {
            "model": self.settings.anthropic_model,
            "max_tokens": self.settings.anthropic_max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                self.api_url,
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()

            result = response.json()
            return result["content"][0]["text"]

    def _parse_content_response(
        self, response: str, platform: Platform, content_format: ContentFormat
    ) -> GeneratedContent:
        """Parse Claude's JSON response into GeneratedContent model."""
        import json

        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]

        try:
            data = json.loads(response.strip())
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response: {e}")
            logger.debug(f"Raw response: {response}")
            raise ValueError(f"Invalid JSON response from Claude: {e}")

        return GeneratedContent(
            platform=platform,
            text=data.get("text", ""),
            hashtags=data.get("hashtags", []),
            cta=data.get("cta"),
            visual_prompt=data.get("visual_prompt", ""),
            content_format=content_format,
        )

    async def generate_content(
        self,
        request: ContentRequest,
        knowledge_context: KnowledgeContext | None = None,
        analytics_report: AnalyticsReport | None = None,
    ) -> list[GeneratedContent]:
        """
        Generate content for all requested platforms.

        Args:
            request: Content generation request
            knowledge_context: Retrieved knowledge base context
            analytics_report: Analytics insights for optimization

        Returns:
            List of GeneratedContent for each platform
        """
        logger.info(
            f"Generating content for topic: '{request.topic}' "
            f"on platforms: {[p.value for p in request.platforms]}"
        )

        system_prompt = self._build_system_prompt(knowledge_context, analytics_report)
        generated_contents: list[GeneratedContent] = []

        for platform in request.platforms:
            try:
                user_prompt = self._build_user_prompt(request, platform)

                logger.info(f"Calling Claude for {platform.value} content...")
                response = await self._call_claude(system_prompt, user_prompt)

                content = self._parse_content_response(
                    response, platform, request.content_format
                )
                generated_contents.append(content)

                logger.info(
                    f"Generated {platform.value} content: "
                    f"{len(content.text)} chars, {len(content.hashtags)} hashtags"
                )

            except Exception as e:
                logger.error(f"Failed to generate content for {platform.value}: {e}")
                continue

        return generated_contents

    async def refine_visual_prompt(
        self,
        base_prompt: str,
        platform: Platform,
        style_preferences: str | None = None,
    ) -> str:
        """
        Refine and enhance a visual prompt for better image generation.

        Args:
            base_prompt: Initial visual prompt
            platform: Target platform for aspect ratio
            style_preferences: Optional style preferences

        Returns:
            Enhanced visual prompt
        """
        constraints = PlatformConstraints.get(platform.value)

        system_prompt = """You are an expert prompt engineer for AI image generation.
Your task is to enhance visual prompts to produce photorealistic, high-quality images.

Requirements:
- Avoid AI artifacts (weird hands, distorted faces, extra limbs)
- Ensure proper composition and framing
- Add specific lighting and color descriptions
- Include camera and lens specifications for realism
- End with quality boosters (8k, photorealistic, etc.)
"""

        user_prompt = f"""Enhance this image generation prompt for {platform.value}:

Original prompt: {base_prompt}

Target aspect ratio: {constraints['image_aspect_ratio']}
Target dimensions: {constraints['image_width']}x{constraints['image_height']}
{f"Style preferences: {style_preferences}" if style_preferences else ""}

Provide ONLY the enhanced prompt, no explanations. 
The prompt should be 150-250 words, extremely detailed."""

        enhanced = await self._call_claude(system_prompt, user_prompt)

        enhanced = enhanced.strip()
        if enhanced.startswith('"') and enhanced.endswith('"'):
            enhanced = enhanced[1:-1]

        if self.settings.default_image_style not in enhanced.lower():
            enhanced += f", {self.settings.default_image_style}"

        logger.info(f"Visual prompt refined: {len(base_prompt)} -> {len(enhanced)} chars")
        return enhanced

    async def generate_variations(
        self,
        content: GeneratedContent,
        num_variations: int = 3,
    ) -> list[GeneratedContent]:
        """
        Generate variations of existing content for A/B testing.

        Args:
            content: Base content to create variations from
            num_variations: Number of variations to generate

        Returns:
            List of content variations
        """
        system_prompt = """You are a social media content optimizer.
Create variations of content that test different:
- Hook styles (question vs statement vs story)
- CTA approaches (direct vs soft vs curiosity-driven)
- Emotional angles (inspiring vs practical vs urgent)

Maintain the core message while varying the delivery."""

        user_prompt = f"""Create {num_variations} variations of this {content.platform.value} post:

Original:
{content.text}

Respond with a JSON array of variations:
[
  {{"text": "variation 1", "hashtags": [...], "cta": "...", "visual_prompt": "..."}},
  ...
]

Keep visual_prompt similar but with slight variations for testing."""

        response = await self._call_claude(system_prompt, user_prompt)

        import json

        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.endswith("```"):
            response = response[:-3]

        variations_data = json.loads(response.strip())
        variations = []

        for var_data in variations_data[:num_variations]:
            variations.append(
                GeneratedContent(
                    platform=content.platform,
                    text=var_data.get("text", ""),
                    hashtags=var_data.get("hashtags", content.hashtags),
                    cta=var_data.get("cta", content.cta),
                    visual_prompt=var_data.get("visual_prompt", content.visual_prompt),
                    content_format=content.content_format,
                )
            )

        logger.info(f"Generated {len(variations)} content variations")
        return variations
