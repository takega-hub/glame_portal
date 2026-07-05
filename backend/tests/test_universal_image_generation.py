import asyncio
import unittest
from unittest import mock

from app.api import settings as settings_module
from app.services.image_generation_service import ImageGenerationService


class UniversalImageGenerationTests(unittest.TestCase):
    def test_openrouter_image_model_filter_excludes_text_models_with_broad_provider_keywords(self):
        raw_models = [
            {"id": "google/gemini-2.5-flash", "name": "Google: Gemini 2.5 Flash", "type": None},
            {"id": "google/gemma-3-27b-it", "name": "Google: Gemma 3 27B", "type": None},
            {"id": "nvidia/nemotron-3-nano-30b-a3b", "name": "NVIDIA: Nemotron 3 Nano", "type": None},
            {"id": "google/gemini-3.1-flash-image-preview", "name": "Google: Nano Banana 2 (Gemini 3.1 Flash Image Preview)", "type": None},
            {"id": "openai/gpt-5-image", "name": "OpenAI: GPT-5 Image", "type": None},
            {"id": "black-forest-labs/flux-pro", "name": "Flux Pro", "type": None},
        ]

        filtered = settings_module._filter_image_generation_models_raw(raw_models)
        filtered_ids = {m["id"] for m in filtered}

        self.assertNotIn("google/gemini-2.5-flash", filtered_ids)
        self.assertNotIn("google/gemma-3-27b-it", filtered_ids)
        self.assertNotIn("nvidia/nemotron-3-nano-30b-a3b", filtered_ids)
        self.assertIn("google/gemini-3.1-flash-image-preview", filtered_ids)
        self.assertIn("openai/gpt-5-image", filtered_ids)
        self.assertIn("black-forest-labs/flux-pro", filtered_ids)

    def test_generate_custom_image_returns_metadata_and_does_not_use_replicate_fallback_by_default(self):
        service = ImageGenerationService()

        async def fake_model():
            return "google/gemini-3.1-flash-image-preview"

        async def fake_openrouter(prompt, model=None, product_images=None, reference_images=None):
            self.assertIn("СТРОГО: не добавляй текст", prompt)
            self.assertEqual(model, "google/gemini-3.1-flash-image-preview")
            self.assertEqual(product_images, ["/static/ref/product.png"])
            self.assertEqual(reference_images, ["/static/models/elena/ref.png"])
            return b"image-bytes"

        async def fake_replicate(prompt, model=None):
            raise AssertionError("Replicate fallback must not be used for product-reference custom generation by default")

        async def fake_upload(image_data, filename, content_type="image/png", storage_subdir="look_images"):
            self.assertEqual(image_data, b"image-bytes")
            self.assertEqual(storage_subdir, "hermes_generated")
            return f"/static/{storage_subdir}/{filename.replace('.png', '.webp')}"

        service._get_model_from_settings = fake_model
        service._generate_with_openrouter = fake_openrouter
        service._generate_with_replicate = fake_replicate
        service._upload_image_to_storage = fake_upload
        service._discover_model_reference_images = lambda model_profile, limit=4: ["/static/models/elena/ref.png"]

        async def run():
            return await service.generate_custom_image(
                prompt="premium GLAME jewelry editorial",
                reference_image_urls=["/static/ref/product.png"],
                model_profile="elena",
                asset_group="hermes_generated",
                filename_prefix="elena_concept",
                provider="openrouter",
            )

        result = asyncio.run(run())

        self.assertEqual(result["provider"], "openrouter")
        self.assertEqual(result["model"], "google/gemini-3.1-flash-image-preview")
        self.assertEqual(result["reference_images_count"], 1)
        self.assertEqual(result["model_reference_images_count"], 1)
        self.assertEqual(result["url"].startswith("/static/hermes_generated/elena_concept_"), True)
        self.assertIn("prompt_used", result)


if __name__ == "__main__":
    unittest.main()
