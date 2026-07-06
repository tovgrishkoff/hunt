"""
Image Generator Module - Replicate API Integration.

Generates high-quality visuals using Flux/Stability AI models
with platform-optimized aspect ratios and photorealistic quality.
"""

import asyncio
import time
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
from .models import GeneratedImage, ImageRequest, Platform

logger = get_logger(__name__)


class ImageGenerator:
    """
    High-quality image generator using Replicate API.

    Supports Flux and Stability AI models for photorealistic
    content creation with platform-specific optimization.
    """

    REPLICATE_API_URL = "https://api.replicate.com/v1"

    NEGATIVE_PROMPT_DEFAULT = (
        "blurry, low quality, distorted, deformed, ugly, bad anatomy, "
        "bad proportions, extra limbs, cloned face, disfigured, "
        "out of frame, watermark, signature, text, logo, "
        "oversaturated, cartoon, anime, illustration, painting, drawing"
    )

    def __init__(self) -> None:
        """Initialize the image generator."""
        self.settings = get_settings()
        self.headers = {
            "Authorization": f"Bearer {self.settings.replicate_api_token}",
            "Content-Type": "application/json",
        }
        self._output_dir = Path("./generated_images")
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def _get_model_input(self, request: ImageRequest) -> dict[str, Any]:
        """Build model-specific input parameters."""
        model = self.settings.image_model.lower()

        base_input = {
            "prompt": request.prompt,
            "width": request.width,
            "height": request.height,
        }

        if "flux" in model:
            return {
                **base_input,
                "aspect_ratio": request.aspect_ratio.replace(":", ":"),
                "output_format": "png",
                "output_quality": 100,
                "safety_tolerance": 2,
                "prompt_upsampling": True,
            }

        elif "stability" in model or "sdxl" in model:
            return {
                **base_input,
                "negative_prompt": request.negative_prompt or self.NEGATIVE_PROMPT_DEFAULT,
                "num_inference_steps": 50,
                "guidance_scale": 7.5,
                "scheduler": "DPMSolverMultistep",
                "refine": "expert_ensemble_refiner",
                "high_noise_frac": 0.8,
            }

        return base_input

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        before_sleep=lambda retry_state: logger.warning(
            f"Retrying Replicate API call, attempt {retry_state.attempt_number}"
        ),
    )
    async def _create_prediction(
        self, model_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a prediction on Replicate."""
        url = f"{self.REPLICATE_API_URL}/predictions"

        payload = {
            "version": self._get_model_version(),
            "input": model_input,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()

    def _get_model_version(self) -> str:
        """Get the model version hash for Replicate."""
        model_versions = {
            "black-forest-labs/flux-1.1-pro": "latest",
            "black-forest-labs/flux-schnell": "latest",
            "stability-ai/sdxl": "latest",
        }

        return model_versions.get(self.settings.image_model, "latest")

    async def _poll_prediction(
        self,
        prediction_id: str,
        max_wait_seconds: int = 300,
        poll_interval: float = 2.0,
    ) -> dict[str, Any]:
        """Poll prediction status until completion."""
        url = f"{self.REPLICATE_API_URL}/predictions/{prediction_id}"
        start_time = time.time()

        async with httpx.AsyncClient(timeout=30.0) as client:
            while time.time() - start_time < max_wait_seconds:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                result = response.json()

                status = result.get("status")
                logger.debug(f"Prediction {prediction_id} status: {status}")

                if status == "succeeded":
                    return result
                elif status == "failed":
                    error = result.get("error", "Unknown error")
                    raise RuntimeError(f"Image generation failed: {error}")
                elif status == "canceled":
                    raise RuntimeError("Image generation was canceled")

                await asyncio.sleep(poll_interval)
                poll_interval = min(poll_interval * 1.2, 10.0)

        raise TimeoutError(
            f"Image generation timed out after {max_wait_seconds} seconds"
        )

    async def _download_image(
        self,
        url: str,
        filename: str,
    ) -> Path:
        """Download generated image to local storage."""
        output_path = self._output_dir / filename

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(url)
            response.raise_for_status()

            output_path.write_bytes(response.content)

        logger.info(f"Image downloaded to {output_path}")
        return output_path

    def create_image_request(
        self,
        prompt: str,
        platform: Platform,
        style: str | None = None,
    ) -> ImageRequest:
        """Create an ImageRequest with platform-appropriate settings."""
        constraints = PlatformConstraints.get(platform.value)

        return ImageRequest(
            prompt=prompt,
            platform=platform,
            aspect_ratio=constraints["image_aspect_ratio"],
            width=constraints["image_width"],
            height=constraints["image_height"],
            style=style or self.settings.default_image_style,
            negative_prompt=self.NEGATIVE_PROMPT_DEFAULT,
        )

    async def generate_image(
        self,
        request: ImageRequest,
        download: bool = True,
    ) -> GeneratedImage:
        """
        Generate a single image from a prompt.

        Args:
            request: Image generation request
            download: Whether to download the image locally

        Returns:
            GeneratedImage with URL and optional local path
        """
        logger.info(
            f"Generating image for {request.platform.value} "
            f"({request.width}x{request.height})"
        )
        logger.debug(f"Prompt: {request.prompt[:100]}...")

        start_time = time.time()

        full_prompt = request.prompt
        if request.style and request.style not in full_prompt:
            full_prompt += f", {request.style}"

        model_input = self._get_model_input(
            ImageRequest(
                **{**request.model_dump(), "prompt": full_prompt}
            )
        )

        prediction = await self._create_prediction(model_input)
        prediction_id = prediction["id"]

        logger.info(f"Prediction created: {prediction_id}")

        result = await self._poll_prediction(prediction_id)

        output = result.get("output")
        if isinstance(output, list):
            image_url = output[0]
        else:
            image_url = output

        generation_time = time.time() - start_time

        local_path = None
        if download:
            timestamp = int(time.time())
            filename = f"{request.platform.value}_{timestamp}.png"
            local_path = await self._download_image(image_url, filename)

        generated_image = GeneratedImage(
            url=image_url,
            local_path=str(local_path) if local_path else None,
            width=request.width,
            height=request.height,
            prompt_used=full_prompt,
            generation_time_seconds=round(generation_time, 2),
            model=self.settings.image_model,
        )

        logger.info(
            f"Image generated in {generation_time:.2f}s | URL: {image_url[:50]}..."
        )

        return generated_image

    async def generate_images_batch(
        self,
        requests: list[ImageRequest],
        max_concurrent: int = 3,
    ) -> list[GeneratedImage]:
        """
        Generate multiple images concurrently.

        Args:
            requests: List of image generation requests
            max_concurrent: Maximum concurrent generations

        Returns:
            List of generated images
        """
        logger.info(f"Starting batch generation of {len(requests)} images")

        semaphore = asyncio.Semaphore(max_concurrent)

        async def generate_with_semaphore(request: ImageRequest) -> GeneratedImage:
            async with semaphore:
                return await self.generate_image(request)

        tasks = [generate_with_semaphore(req) for req in requests]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        images: list[GeneratedImage] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to generate image {i}: {result}")
            else:
                images.append(result)

        logger.info(f"Batch complete: {len(images)}/{len(requests)} successful")
        return images

    async def generate_variations(
        self,
        base_prompt: str,
        platform: Platform,
        num_variations: int = 3,
    ) -> list[GeneratedImage]:
        """
        Generate variations of an image for A/B testing.

        Args:
            base_prompt: Base visual prompt
            platform: Target platform
            num_variations: Number of variations to generate

        Returns:
            List of image variations
        """
        variation_modifiers = [
            "warm golden hour lighting, soft shadows",
            "cool blue tones, modern minimalist aesthetic",
            "dramatic contrast, cinematic composition",
            "soft natural daylight, lifestyle photography",
            "vibrant colors, high energy composition",
        ]

        requests = []
        for i in range(num_variations):
            modifier = variation_modifiers[i % len(variation_modifiers)]
            varied_prompt = f"{base_prompt}, {modifier}"
            request = self.create_image_request(varied_prompt, platform)
            requests.append(request)

        return await self.generate_images_batch(requests)

    def cleanup_old_images(self, max_age_hours: int = 24) -> int:
        """Remove generated images older than specified age."""
        import os

        cutoff_time = time.time() - (max_age_hours * 3600)
        removed_count = 0

        for file_path in self._output_dir.iterdir():
            if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                file_path.unlink()
                removed_count += 1

        logger.info(f"Cleaned up {removed_count} old images")
        return removed_count
