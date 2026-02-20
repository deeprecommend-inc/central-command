"""
Vision CAPTCHA Solver - GPT-4o Vision-based image CAPTCHA solver

Uses OpenAI GPT-4o to analyze and solve visual CAPTCHAs:
- Standard image CAPTCHAs (distorted text)
- reCAPTCHA image challenges (grid selection)
- hCaptcha image challenges
- Text-based visual CAPTCHAs
"""
from __future__ import annotations

import base64
import time
from typing import Optional

from loguru import logger

from .captcha_solver import CaptchaSolver, CaptchaInfo, CaptchaSolution, CaptchaType


class VisionCaptchaSolver(CaptchaSolver):
    """
    CAPTCHA solver using OpenAI GPT-4o Vision.

    Sends CAPTCHA images to GPT-4o for visual analysis and text extraction.
    Supports image CAPTCHAs and text CAPTCHAs that require visual recognition.

    Example:
        solver = VisionCaptchaSolver(api_key="sk-...")
        solution = await solver.solve(captcha_info)
        if solution.success:
            print(f"Text: {solution.text}")
    """

    SUPPORTED_TYPES = {CaptchaType.IMAGE, CaptchaType.TEXT}

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        timeout: float = 30.0,
        base_url: str = "",
    ):
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._base_url = base_url

    def supports(self, captcha_type: CaptchaType) -> bool:
        return captcha_type in self.SUPPORTED_TYPES

    async def solve(self, captcha: CaptchaInfo) -> CaptchaSolution:
        """Solve CAPTCHA using GPT-4o Vision"""
        import openai

        start_time = time.time()

        if not captcha.image_data:
            return CaptchaSolution(
                success=False,
                error="No image data provided",
                provider="vision",
            )

        try:
            image_b64 = base64.b64encode(captcha.image_data).decode()
            prompt = self._build_prompt(captcha.captcha_type)

            client_kwargs = {"api_key": self._api_key}
            if self._base_url:
                client_kwargs["base_url"] = self._base_url
            client = openai.AsyncOpenAI(**client_kwargs)
            response = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_b64}",
                                },
                            },
                        ],
                    }
                ],
                max_tokens=256,
                timeout=self._timeout,
            )

            answer = response.choices[0].message.content.strip()
            solve_time = int((time.time() - start_time) * 1000)

            logger.info(f"Vision solver response: {answer} ({solve_time}ms)")

            # Extract clean answer (remove quotes, extra whitespace)
            clean_answer = self._extract_answer(answer)

            if clean_answer:
                return CaptchaSolution(
                    success=True,
                    text=clean_answer,
                    solve_time_ms=solve_time,
                    provider="vision",
                )
            else:
                return CaptchaSolution(
                    success=False,
                    error="Could not extract answer from vision response",
                    solve_time_ms=solve_time,
                    provider="vision",
                )

        except Exception as e:
            solve_time = int((time.time() - start_time) * 1000)
            logger.error(f"Vision solver error: {e}")
            return CaptchaSolution(
                success=False,
                error=str(e),
                solve_time_ms=solve_time,
                provider="vision",
            )

    def _build_prompt(self, captcha_type: CaptchaType) -> str:
        """Build prompt based on CAPTCHA type"""
        if captcha_type == CaptchaType.IMAGE:
            return (
                "This image contains a CAPTCHA. "
                "Read the text or numbers shown in the image. "
                "If it is a grid-based image selection challenge, "
                "identify which grid cells match the description and return their positions "
                "as comma-separated numbers (1-based, left-to-right, top-to-bottom). "
                "Reply with ONLY the answer text or grid positions. No explanation."
            )
        else:
            # TEXT type
            return (
                "This image contains text that needs to be read. "
                "What text or characters are shown in this image? "
                "Reply with ONLY the exact text. No explanation."
            )

    def _extract_answer(self, raw: str) -> Optional[str]:
        """Extract clean answer from model response"""
        if not raw:
            return None
        # Strip common wrapper patterns
        answer = raw.strip().strip('"').strip("'").strip("`").strip()
        # Remove common prefix patterns
        for prefix in ["Answer:", "Text:", "CAPTCHA:", "The text is", "The answer is"]:
            if answer.lower().startswith(prefix.lower()):
                answer = answer[len(prefix):].strip().strip(":").strip()
        return answer if answer else None

    async def get_balance(self) -> float:
        """OpenAI API does not support balance queries"""
        return -1.0
