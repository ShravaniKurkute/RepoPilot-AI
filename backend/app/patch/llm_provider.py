"""AI generation engine interfacing with Google Gemini and deterministic mock providers for patch synthesis."""

import abc
import asyncio
import json
import re
import time
from typing import Any, Dict, List, Optional
import google.genai as genai
from google.genai import types

from app.core.config import settings
from app.core.logging import logger


class BasePatchLLMProvider(abc.ABC):
    """Abstract interface for fix planning and patch synthesis."""

    @abc.abstractmethod
    async def generate_fix_plan(self, prompt_text: str) -> Dict[str, Any]:
        """Generates a structured implementation plan from issue and repository context."""
        pass

    @abc.abstractmethod
    async def generate_patch_diff(self, prompt_text: str) -> str:
        """Generates unified-diff code modifications matching the approved plan."""
        pass


class GeminiPatchLLMProvider(BasePatchLLMProvider):
    """Google Gemini model client generating structured plans and unified diffs."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ):
        self._api_key = api_key or settings.GEMINI_API_KEY
        self._model = model_name or settings.AI_ANALYSIS_MODEL
        self._timeout = timeout if timeout is not None else settings.gemini_request_timeout
        self._max_retries = max_retries if max_retries is not None else settings.ANALYSIS_MAX_RETRIES
        self._client: Optional[genai.Client] = None

    def _normalize_model(self) -> str:
        name = (self._model or "").strip()
        if name.startswith("models/"):
            return name[7:]
        return name

    def _get_client(self) -> genai.Client:
        if self._client is None:
            http_options = types.HttpOptions(timeout=int(self._timeout * 1000.0))
            self._client = genai.Client(api_key=self._api_key, http_options=http_options)
            # Disable speakeasy retry loop that could sleep for excessive Retry-After durations
            try:
                if hasattr(self._client.aio, "interactions") and hasattr(self._client.aio.interactions, "sdk_configuration"):
                    self._client.aio.interactions.sdk_configuration.retry_config = None
            except Exception:
                pass
        return self._client

    def _sanitize_error(self, message: str) -> str:
        if not message:
            return ""
        if self._api_key and self._api_key in message:
            message = message.replace(self._api_key, "[REDACTED_API_KEY]")
        return message

    def _extract_retry_after(self, error: Exception) -> Optional[float]:
        resp = getattr(error, "response", None)
        if resp and hasattr(resp, "headers"):
            retry_val = resp.headers.get("retry-after")
            if retry_val:
                try:
                    return float(retry_val)
                except ValueError:
                    pass
        err_str = str(error).lower()
        match = re.search(r"(?:retry[- ]after|try again in|retry in)[:\s]+(\d+(?:\.\d+)?)", err_str)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return None

    def _extract_text_from_interaction(self, interaction: Any) -> str:
        output_text = getattr(interaction, "output_text", None)
        if output_text and isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        text_attr = getattr(interaction, "text", None)
        if text_attr and isinstance(text_attr, str) and text_attr.strip():
            return text_attr.strip()
        steps = getattr(interaction, "steps", None)
        if isinstance(steps, list):
            parts: List[str] = []
            for step in steps:
                if getattr(step, "type", None) == "thought":
                    continue
                content = getattr(step, "content", None)
                if isinstance(content, list):
                    for item in content:
                        text_val = getattr(item, "text", None)
                        if text_val and isinstance(text_val, str):
                            parts.append(text_val)
            if parts:
                return "".join(parts).strip()
        return ""

    async def _call_llm(self, prompt: str, system_instruction: str, mime_type: str = "application/json") -> str:
        client = self._get_client()
        primary_model = self._normalize_model()

        # Build candidate list: primary model first, followed by resilient available fallbacks
        candidate_models = [primary_model]
        for fallback in ("gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"):
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        call_budget = min(self._timeout, 45.0)
        last_error = None

        for model_idx, model_name in enumerate(candidate_models):
            delay = 1.0
            model_t0 = time.time()
            logger.info(
                "[GeminiPatchLLM] Attempting generation with model '%s' (candidate %d/%d, mime_type=%s, timeout=%.1fs)...",
                model_name,
                model_idx + 1,
                len(candidate_models),
                mime_type,
                call_budget,
            )

            max_attempts = min(self._max_retries, 2)
            for attempt in range(max_attempts):
                try:
                    # 1. Primary path: Interactions API with tight wait_for guard
                    text = ""
                    try:
                        interaction = await asyncio.wait_for(
                            client.aio.interactions.create(
                                model=model_name,
                                input=prompt,
                                system_instruction=system_instruction,
                                response_format={"type": "text", "mime_type": mime_type},
                                generation_config={"thinking_level": "low"},
                                timeout=call_budget,
                            ),
                            timeout=call_budget,
                        )
                        text = self._extract_text_from_interaction(interaction)
                    except Exception as inter_err:
                        inter_err_str = str(inter_err)
                        # If Interactions API times out, fails, or is unsupported, route to models.generate_content
                        logger.debug(
                            "[GeminiPatchLLM] Interactions API call not usable for '%s' (%s). Routing to models.generate_content.",
                            model_name,
                            self._sanitize_error(inter_err_str),
                        )
                        gen_resp = await asyncio.wait_for(
                            client.aio.models.generate_content(
                                model=model_name,
                                contents=prompt,
                                config={
                                    "system_instruction": system_instruction,
                                    "response_mime_type": mime_type,
                                    "http_options": {"timeout": int(call_budget * 1000.0)},
                                },
                            ),
                            timeout=call_budget,
                        )
                        text = getattr(gen_resp, "text", "") or ""

                    if text and text.strip():
                        elapsed = time.time() - model_t0
                        logger.info(
                            "[GeminiPatchLLM] Succeeded generation with model '%s' in %.2fs (response length=%d).",
                            model_name,
                            elapsed,
                            len(text),
                        )
                        return text

                    # Empty text returned
                    logger.warning("[GeminiPatchLLM] Empty response received from model '%s' on attempt %d.", model_name, attempt + 1)

                except Exception as e:
                    last_error = e
                    err_str = str(e)
                    sanitized_msg = self._sanitize_error(err_str)

                    # Permanent authentication error
                    if any(code in err_str for code in ("401", "API_KEY_INVALID")):
                        raise RuntimeError(f"Gemini API authentication failed (401): {sanitized_msg}") from e

                    # Check for quota exhaustion / rate limit (429 RESOURCE_EXHAUSTED)
                    is_quota_exhausted = any(
                        indicator in err_str.lower()
                        for indicator in ("429", "resource_exhausted", "quota exceeded", "limit exceeded", "free tier")
                    )
                    retry_after = self._extract_retry_after(e)

                    if is_quota_exhausted and (retry_after is None or retry_after > 15.0 or "day" in err_str.lower()):
                        logger.warning(
                            "[GeminiPatchLLM] Daily free-tier quota exhausted for model '%s' (429 RESOURCE_EXHAUSTED). Will check next candidate model.",
                            model_name,
                        )
                        # Break attempt loop to move immediately to the next candidate model
                        break

                    # Check for 404 Not Found (e.g. model retired or unsupported)
                    if "404" in err_str or "not found" in err_str.lower() or "no longer available" in err_str.lower():
                        logger.warning("[GeminiPatchLLM] Model '%s' not available (404 Not Found). Trying fallback candidate.", model_name)
                        break

                    # Transient retry with small bounded backoff
                    if attempt < max_attempts - 1:
                        backoff = min(max(retry_after or delay, 1.0), 5.0)
                        logger.warning(
                            "[GeminiPatchLLM] Transient error on '%s' (%s). Retrying in %.1fs...",
                            model_name,
                            sanitized_msg,
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                        delay = min(delay * 2, 5.0)
                        continue

        # If all candidates exhausted, fail with clean, descriptive message
        sanitized_last = self._sanitize_error(str(last_error))
        if any(indicator in sanitized_last.lower() for indicator in ("429", "resource_exhausted", "quota", "limit exceeded")):
            raise RuntimeError(
                f"Gemini API daily quota exceeded across available models (429 RESOURCE_EXHAUSTED). "
                f"Please verify Gemini API billing or configure AI_ANALYSIS_PROVIDER=mock in backend/.env for offline testing."
            )

        if "timeout" in sanitized_last.lower():
            raise RuntimeError(
                f"Gemini patch LLM request timed out after {call_budget}s: {sanitized_last}"
            )

        raise RuntimeError(f"Gemini patch LLM generation failed: {sanitized_last}")

    async def generate_fix_plan(self, prompt_text: str) -> Dict[str, Any]:
        system_instruction = (
            "You are RepoPilot AI's Senior Software Architect and Automated Fix Planning Engine.\n"
            "Analyze the bug details, AST relationships, and RAG context to formulate a robust remediation plan.\n"
            "Return valid JSON conforming to the requested schema. Do not write code patches yet."
        )
        raw_json = await self._call_llm(prompt_text, system_instruction, mime_type="application/json")
        return self._safe_parse_json(raw_json)

    async def generate_patch_diff(self, prompt_text: str) -> str:
        system_instruction = (
            "You are RepoPilot AI's Autonomous Code Patch Synthesis Engine.\n"
            "Generate an exact, syntactically valid unified diff (diff -u) repairing the targeted bug.\n"
            "Requirements:\n"
            "- Output ONLY the unified diff block starting with '--- a/' and '+++ b/'.\n"
            "- Do NOT wrap in explanatory markdown or conversational text.\n"
            "- Do NOT modify unrelated lines or refactor formatting.\n"
            "- Ensure exact line numbers and context lines match the source code."
        )
        raw_diff = await self._call_llm(prompt_text, system_instruction, mime_type="text/plain")
        return self._clean_diff(raw_diff)

    def _safe_parse_json(self, raw_text: str) -> Dict[str, Any]:
        if not raw_text or not raw_text.strip():
            return {}
        clean = raw_text.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()
        try:
            return json.loads(clean)
        except Exception:
            match = re.search(r"\{.*\}", clean, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
            return {}

    def _clean_diff(self, raw_text: str) -> str:
        clean = raw_text.strip()
        if clean.startswith("```diff"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        return clean.strip()


class MockPatchLLMProvider(BasePatchLLMProvider):
    """Deterministic, offline fix planner and patch generator for development and automated testing."""

    async def generate_fix_plan(self, prompt_text: str) -> Dict[str, Any]:
        # Extract target file from prompt
        file_match = re.search(r"TARGET FILE:\s*([^\s\n]+)", prompt_text)
        target_file = file_match.group(1) if file_match else "main.py"

        issue_match = re.search(r"ISSUE TITLE:\s*([^\n]+)", prompt_text)
        issue_title = issue_match.group(1).strip() if issue_match else "Detected Defect"

        # Domain-specific plans for standard verification cases
        if "calculate_average" in prompt_text or "total / len(numbers)" in prompt_text:
            return {
                "summary": f"Prevent ZeroDivisionError when calculating average of empty list in {target_file}",
                "root_cause": "Division by len(numbers) occurs without verifying if the list is empty.",
                "proposed_solution": "Introduce defensive guard clause checking if numbers is empty and return 0.0.",
                "implementation_steps": [
                    f"Inspect calculate_average in {target_file}",
                    "Add guard: if not numbers: return 0.0",
                    "Proceed with division when list has elements",
                ],
                "affected_files": [target_file],
                "risk_level": "Low",
                "expected_behavior": "calculate_average([]) returns 0.0 instead of crashing with ZeroDivisionError.",
                "recommended_tests": [
                    "test_calculate_average_empty_list",
                    "test_calculate_average_positive_numbers",
                ],
            }

        if "get_user" in prompt_text or "sql_injection" in prompt_text.lower():
            return {
                "summary": f"Remediate SQL injection vulnerability in get_user in {target_file}",
                "root_cause": "Direct concatenation of untrusted user_id into raw SQL query string.",
                "proposed_solution": "Use parameterized query placeholders (:user_id) rather than raw string concatenation.",
                "implementation_steps": [
                    f"Inspect get_user in {target_file}",
                    "Replace raw string concatenation with parameterized placeholder",
                    "Ensure user_id is bound safely via DB parameter binding",
                ],
                "affected_files": [target_file],
                "risk_level": "High",
                "expected_behavior": "Query string uses safe parameterized placeholder, neutralizing injection.",
                "recommended_tests": [
                    "test_get_user_parameterized_query",
                    "test_get_user_sql_injection_payload_neutralized",
                ],
            }

        if "find_maximum" in prompt_text or "maximum = 0" in prompt_text or "maximum initialization" in prompt_text.lower():
            return {
                "summary": f"Fix incorrect maximum initialization for negative collections in {target_file}",
                "root_cause": "maximum is hardcoded to 0, which yields incorrect results for collections containing only negative numbers.",
                "proposed_solution": "Initialize maximum to numbers[0] with an empty collection guard clause returning None.",
                "implementation_steps": [
                    f"Inspect find_maximum in {target_file}",
                    "Add empty collection guard clause returning None",
                    "Initialize maximum to numbers[0] instead of 0",
                ],
                "affected_files": [target_file],
                "risk_level": "Low",
                "expected_behavior": "find_maximum([-5, -2, -9]) correctly returns -2 instead of 0.",
                "recommended_tests": [
                    "test_find_maximum_negative_numbers",
                    "test_find_maximum_empty_list",
                ],
            }

        return {
            "summary": f"Remediate {issue_title} in {target_file}",
            "root_cause": "Unchecked operation or improper input sanitization in control flow.",
            "proposed_solution": "Introduce defensive input guard checks and sanitize target variables before processing.",
            "implementation_steps": [
                f"Inspect parameters in {target_file}",
                "Add defensive verification guard clause",
                "Ensure return value adheres to function signature",
            ],
            "affected_files": [target_file],
            "risk_level": "Low",
            "expected_behavior": "Function executes safely without runtime exceptions or vulnerabilities.",
            "recommended_tests": [
                f"Test boundary conditions for {target_file}",
                "Verify normal path behavior remains unchanged",
            ],
        }

    async def generate_patch_diff(self, prompt_text: str) -> str:
        file_match = re.search(r"TARGET FILE:\s*([^\s\n]+)", prompt_text)
        target_file = file_match.group(1) if file_match else "main.py"

        # Check evidence snippet
        evidence_match = re.search(r"EVIDENCE:\s*```[^\n]*\n(.*?)```", prompt_text, re.DOTALL)
        evidence = evidence_match.group(1).strip() if evidence_match else "pass"

        # Check for specific bug types to synthesize targeted fixes
        if "calculate_average" in prompt_text or "total / len(numbers)" in prompt_text:
            return (
                f"--- a/{target_file}\n"
                f"+++ b/{target_file}\n"
                f"@@ -1,4 +1,6 @@\n"
                f" def calculate_average(numbers):\n"
                f"+    if not numbers:\n"
                f"+        return 0.0\n"
                f"     total = sum(numbers)\n"
                f"     average = total / len(numbers)\n"
                f"     return average\n"
            )

        if "find_maximum" in prompt_text or "maximum = 0" in prompt_text or "find_maximum" in target_file:
            return (
                f"--- a/{target_file}\n"
                f"+++ b/{target_file}\n"
                f"@@ -12,4 +12,6 @@\n"
                f" def find_maximum(numbers):\n"
                f"+    if not numbers:\n"
                f"+        return None\n"
                f"-    maximum = 0\n"
                f"+    maximum = numbers[0]\n"
                f" \n"
                f"     for num in numbers:\n"
            )

        if "SELECT * FROM users WHERE id = \" + user_id" in prompt_text or ('query = "SELECT * FROM users' in prompt_text and "+ user_id" in prompt_text):
            return (
                f"--- a/{target_file}\n"
                f"+++ b/{target_file}\n"
                f"@@ -7,3 +7,3 @@\n"
                f" def get_user(user_id):\n"
                f"-    query = \"SELECT * FROM users WHERE id = \" + user_id\n"
                f"+    query = \"SELECT * FROM users WHERE id = :user_id\"\n"
                f"     return query\n"
            )

        if "total / 0" in prompt_text or "division_by_zero" in prompt_text.lower():
            return (
                f"--- a/{target_file}\n"
                f"+++ b/{target_file}\n"
                f"@@ -1,4 +1,6 @@\n"
                f" def compute_ratio(total, count):\n"
                f"+    if count == 0 or count is None:\n"
                f"+        return 0.0\n"
                f"-    ratio = total / 0\n"
                f"+    ratio = total / count\n"
                f"     return ratio\n"
            )

        if "SELECT * FROM users" in prompt_text or "sql_injection" in prompt_text.lower():
            return (
                f"--- a/{target_file}\n"
                f"+++ b/{target_file}\n"
                f"@@ -1,3 +1,3 @@\n"
                f" def get_user(user_id):\n"
                f"-    query = f\"SELECT * FROM users WHERE id = '{{user_id}}'\"\n"
                f"+    query = \"SELECT * FROM users WHERE id = :user_id\"\n"
                f"     return query\n"
            )

        # Generic safe diff fallback
        first_ev_line = evidence.splitlines()[0] if evidence else "pass"
        return (
            f"--- a/{target_file}\n"
            f"+++ b/{target_file}\n"
            f"@@ -1,2 +1,3 @@\n"
            f"+    # Applied defensive validation guard\n"
            f"     {first_ev_line}\n"
        )


def get_patch_llm_provider() -> BasePatchLLMProvider:
    """Factory creating the active Patch LLM Provider based on application configuration."""
    provider_type = settings.AI_ANALYSIS_PROVIDER.lower().strip()
    if provider_type == "mock" or not settings.is_gemini_configured:
        return MockPatchLLMProvider()

    return GeminiPatchLLMProvider(
        api_key=settings.GEMINI_API_KEY,
        model_name=settings.AI_ANALYSIS_MODEL,
        timeout=settings.gemini_request_timeout,
        max_retries=settings.ANALYSIS_MAX_RETRIES,
    )

