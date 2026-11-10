"""AI analyzer client interfacing with Google Gemini and offline deterministic test analyzers."""

import abc
import asyncio
import json
import re
from typing import Any, Dict, List, Optional
import google.genai as genai
from google.genai import types

from app.analysis.context_builder import AnalysisContext
from app.analysis.prompts import SYSTEM_ANALYSIS_INSTRUCTION, format_analysis_prompt
from app.core.config import settings
from app.core.logging import logger


class BaseCodeAnalyzer(abc.ABC):
    """Abstract interface for code analysis engines."""

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Name of analyzer provider."""
        pass

    @abc.abstractmethod
    async def analyze_context(self, context: AnalysisContext) -> List[Dict[str, Any]]:
        """Analyzes a code slice and returns a list of raw discovered issues."""
        pass


class GeminiCodeAnalyzer(BaseCodeAnalyzer):
    """Google Gemini AI analyzer generating schema-enforced structured findings via Google GenAI SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        max_retries: Optional[int] = None,
        timeout: Optional[float] = None,
    ):
        self._api_key = api_key or settings.GEMINI_API_KEY
        self._model = model_name or settings.AI_ANALYSIS_MODEL
        self._max_retries = max_retries if max_retries is not None else settings.ANALYSIS_MAX_RETRIES
        self._timeout = timeout if timeout is not None else settings.gemini_request_timeout
        self._client: Optional[genai.Client] = None

        if not self._api_key:
            logger.warning(
                "GeminiCodeAnalyzer initialized without GEMINI_API_KEY. "
                "AI code analysis will fail unless API key is set in .env."
            )

    @property
    def provider_name(self) -> str:
        return f"gemini ({self._normalize_model()})"

    def _normalize_model(self) -> str:
        name = (self._model or "").strip()
        if name.startswith("models/"):
            return name[7:]
        return name

    def _get_client(self) -> genai.Client:
        if self._client is None:
            # Configure transport-level timeout in milliseconds on HttpOptions
            http_options = types.HttpOptions(
                timeout=int(self._timeout * 1000.0)
            )
            self._client = genai.Client(
                api_key=self._api_key,
                http_options=http_options,
            )
        return self._client

    def _sanitize_error(self, message: str) -> str:
        """Removes sensitive API keys from error messages before logging or raising."""
        if not message:
            return ""
        if self._api_key and self._api_key in message:
            message = message.replace(self._api_key, "[REDACTED_API_KEY]")
        return message

    def _extract_retry_after(self, error: Exception) -> Optional[float]:
        """Extracts Retry-After duration in seconds from response headers or error messages."""
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
        """Extracts text content from an Interaction or model response object."""
        # 1. Direct output_text attribute (standard for Interaction responses)
        output_text = getattr(interaction, "output_text", None)
        if output_text and isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        # 2. Text attribute (standard for generate_content response objects)
        text_attr = getattr(interaction, "text", None)
        if text_attr and isinstance(text_attr, str) and text_attr.strip():
            return text_attr.strip()

        # 3. Fallback extraction from interaction steps
        steps = getattr(interaction, "steps", None)
        if isinstance(steps, list):
            parts: List[str] = []
            for step in steps:
                step_type = getattr(step, "type", None)
                if step_type == "thought":
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

    async def analyze_context(self, context: AnalysisContext) -> List[Dict[str, Any]]:
        """Sends target code, AST info, and RAG context to Gemini via Google GenAI SDK."""
        if not self._api_key:
            raise ValueError(
                "GEMINI_API_KEY is not configured. Please supply a valid key in .env "
                "or set AI_ANALYSIS_PROVIDER=mock for offline usage."
            )

        prompt_text = format_analysis_prompt(
            file_path=context.file_path,
            language=context.language,
            start_line=context.start_line,
            end_line=context.end_line,
            symbol_name=context.symbol_name or "<file_scope>",
            symbol_type=context.symbol_type or "module",
            target_code=context.target_code,
            ast_summary=context.ast_summary,
            imports_list=context.imports_context,
            rag_contexts=context.related_rag_contexts,
        )

        model_name = self._normalize_model()
        client = self._get_client()

        delay = 2.0
        last_error = None

        for attempt in range(self._max_retries):
            try:
                # Primary path: Official Google GenAI SDK Interactions API with fast fallback to generate_content
                try:
                    interaction = await asyncio.wait_for(
                        client.aio.interactions.create(
                            model=model_name,
                            input=prompt_text,
                            system_instruction=SYSTEM_ANALYSIS_INSTRUCTION,
                            response_format={"type": "text", "mime_type": "application/json"},
                            generation_config={"thinking_level": "low"},
                        ),
                        timeout=min(self._timeout, 5.0),
                    )
                    raw_text = self._extract_text_from_interaction(interaction)
                    if raw_text:
                        return self._safe_parse_json(raw_text)
                except Exception as inter_err:
                    inter_err_str = str(inter_err)
                    # Permanent auth errors (401, 403) or client-side timeouts must bubble directly to outer handler
                    if any(code in inter_err_str for code in ("401", "API_KEY_INVALID", "403", "PERMISSION_DENIED", "client-side timeout")):
                        raise inter_err

                    # Route to SDK generate_content
                    if hasattr(client, "aio") and hasattr(client.aio, "models") and hasattr(client.aio.models, "generate_content"):
                        try:
                            gen_call = client.aio.models.generate_content(
                                model=model_name,
                                contents=prompt_text,
                                config={
                                    "system_instruction": SYSTEM_ANALYSIS_INSTRUCTION,
                                    "response_mime_type": "application/json",
                                    "http_options": {"timeout": int(self._timeout * 1000.0)},
                                },
                            )
                            if asyncio.iscoroutine(gen_call):
                                gen_resp = await gen_call
                                raw_text = getattr(gen_resp, "text", "") or ""
                                if raw_text:
                                    return self._safe_parse_json(raw_text)
                        except Exception as gen_err:
                            raise gen_err
                    raise inter_err

                return []

            except Exception as e:
                last_error = e
                err_str = str(e)
                sanitized_msg = self._sanitize_error(err_str)

                # Permanent errors: fail immediately without retrying
                is_permanent = any(
                    code in err_str
                    for code in (
                        "401",
                        "API_KEY_INVALID",
                        "403",
                        "PERMISSION_DENIED",
                        "404",
                        "not found",
                        "no longer available",
                    )
                )

                if is_permanent:
                    if "401" in err_str or "API_KEY_INVALID" in err_str:
                        raise RuntimeError(
                            "Gemini API authentication failed (401 Unauthorized). "
                            "Please verify GEMINI_API_KEY in backend/.env."
                        ) from e
                    if "404" in err_str:
                        raise RuntimeError(
                            f"Gemini API model '{model_name}' error (404 Not Found): {sanitized_msg}"
                        ) from e
                    raise RuntimeError(f"Gemini API permanent error: {sanitized_msg}") from e

                # Check for rate limiting / high demand / transient errors / timeouts
                is_transient = any(
                    code in err_str
                    for code in (
                        "429",
                        "500",
                        "502",
                        "503",
                        "504",
                        "RESOURCE_EXHAUSTED",
                        "high demand",
                        "UNAVAILABLE",
                    )
                ) or "timeout" in err_str.lower()

                if is_transient:
                    retry_after = self._extract_retry_after(e)
                    # If daily quota limit exceeded (or retry_after > 120s), retrying is futile; fail fast immediately
                    if (retry_after is not None and retry_after > 120.0) or "per day" in err_str.lower() or "limit exceeded" in err_str.lower():
                        raise RuntimeError(
                            f"Gemini API daily quota exceeded ({sanitized_msg}). "
                            "Please upgrade plan, wait for quota reset, or configure an alternative model."
                        ) from e

                    if attempt < self._max_retries - 1:
                        backoff = min(max(retry_after, 1.0), 60.0) if retry_after is not None else min(delay, 60.0)
                        logger.warning(
                            "Gemini API transient error (%s). Attempt %d/%d. Retrying in %.1fs...",
                            sanitized_msg,
                            attempt + 1,
                            self._max_retries,
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                        delay = min(delay * 2, 60.0)
                        continue

                # Retries exhausted or non-transient error
                if "503" in err_str or "high demand" in err_str.lower():
                    raise RuntimeError(
                        f"Google Gemini model '{model_name}' is currently experiencing high demand (503 Service Unavailable). "
                        "Please retry shortly or configure an alternative model in backend/.env."
                    ) from e
                if "timeout" in err_str.lower():
                    raise RuntimeError(
                        f"Gemini code analysis request timed out after {self._timeout}s: {sanitized_msg}"
                    ) from e

                raise RuntimeError(f"Gemini code analysis failed: {sanitized_msg}") from e

        raise RuntimeError(
            f"Gemini code analysis failed after {self._max_retries} retries: {self._sanitize_error(str(last_error))}"
        )

    def _safe_parse_json(self, raw_text: str) -> List[Dict[str, Any]]:
        """Parses LLM JSON response safely, handling markdown fences and schemas."""
        if not raw_text or not raw_text.strip():
            return []

        clean = raw_text.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()

        try:
            data = json.loads(clean)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("issues", [])
            return []
        except json.JSONDecodeError:
            # Fallback regex search for JSON array or object
            bracket_match = re.search(r"\[\s*\{.*\}\s*\]", clean, re.DOTALL)
            if bracket_match:
                try:
                    data = json.loads(bracket_match.group(0))
                    if isinstance(data, list):
                        return data
                except Exception:
                    pass
            brace_match = re.search(r'\{\s*"issues"\s*:\s*\[.*\]\s*\}', clean, re.DOTALL)
            if brace_match:
                try:
                    data = json.loads(brace_match.group(0))
                    return data.get("issues", [])
                except Exception:
                    pass

            logger.warning("Failed to parse JSON response from Gemini: %s", clean[:120])
            return []


class MockCodeAnalyzer(BaseCodeAnalyzer):
    """Deterministic, offline analyzer using AST pattern heuristics for testing."""

    @property
    def provider_name(self) -> str:
        return "mock-analyzer (offline)"

    async def analyze_context(self, context: AnalysisContext) -> List[Dict[str, Any]]:
        """Scans code for common vulnerability patterns deterministically."""
        issues: List[Dict[str, Any]] = []
        lines = context.target_code.splitlines()
        start_offset = context.start_line

        for idx, line in enumerate(lines, start=start_offset):
            stripped = line.strip()

            # 1. SQL Injection Pattern
            if re.search(r'(?:SELECT|INSERT|UPDATE|DELETE)\s+.*\{', line, re.IGNORECASE) or re.search(
                r'execute\(f["\']', line
            ):
                issues.append(
                    {
                        "issue_title": "SQL Injection via String Interpolation",
                        "issue_description": "SQL statement constructed dynamically with unparameterized variables.",
                        "category": "security_vulnerability",
                        "subcategory": "sql_injection",
                        "severity": "Critical",
                        "confidence_score": 0.95,
                        "start_line": idx,
                        "end_line": idx,
                        "affected_symbol": context.symbol_name,
                        "evidence": stripped,
                        "technical_explanation": (
                            "Direct string formatting into SQL queries allows attacker-supplied input "
                            "to alter SQL execution logic, enabling unauthorized data extraction or destruction."
                        ),
                        "potential_impact": "Full database breach, data alteration, or privilege escalation.",
                        "suggested_fix": "Use parameterized queries with bound placeholders or an ORM.",
                        "cwe_id": "CWE-89",
                    }
                )

            # 2. Path Traversal Pattern
            if re.search(r'open\(.*(?:filename|user_path|file_name|request\.args)', line, re.IGNORECASE) and not re.search(
                r'basename|abspath', line
            ):
                issues.append(
                    {
                        "issue_title": "Path Traversal in File Access",
                        "issue_description": "File path constructed from input without canonicalization or validation.",
                        "category": "security_vulnerability",
                        "subcategory": "path_traversal",
                        "severity": "High",
                        "confidence_score": 0.90,
                        "start_line": idx,
                        "end_line": idx,
                        "affected_symbol": context.symbol_name,
                        "evidence": stripped,
                        "technical_explanation": (
                            "Unsanitized paths containing '../' sequences allow attackers to read or write files "
                            "outside the intended storage directory."
                        ),
                        "potential_impact": "Unauthorized file disclosure or remote code execution via file overwrite.",
                        "suggested_fix": "Validate path against allowed root with os.path.realpath() and os.path.commonpath().",
                        "cwe_id": "CWE-22",
                    }
                )

            # 3. Hardcoded Secret Pattern
            if re.search(r'(?:api_key|password|secret|jwt_secret)\s*=\s*["\'][a-zA-Z0-9_\-\.]{8,}["\']', line, re.IGNORECASE):
                issues.append(
                    {
                        "issue_title": "Hardcoded Secret / Credential",
                        "issue_description": "Cryptographic key or credential embedded in source code.",
                        "category": "security_vulnerability",
                        "subcategory": "hardcoded_credentials",
                        "severity": "High",
                        "confidence_score": 0.92,
                        "start_line": idx,
                        "end_line": idx,
                        "affected_symbol": context.symbol_name,
                        "evidence": stripped,
                        "technical_explanation": (
                            "Hardcoded credentials in source code can be exposed in version control, logs, "
                            "or client binaries, giving attackers unauthorized access to sensitive APIs."
                        ),
                        "potential_impact": "Unauthorized access to internal systems and third-party APIs.",
                        "suggested_fix": "Load credentials from environment variables or a secrets manager.",
                        "cwe_id": "CWE-798",
                    }
                )

            # 4. Division by Zero Pattern
            if re.search(r'/\s*0(?:\b|\.0|\))', line):
                issues.append(
                    {
                        "issue_title": "Division by Zero Error",
                        "issue_description": "Arithmetic division with constant or unchecked zero denominator.",
                        "category": "logic_bug",
                        "subcategory": "division_by_zero",
                        "severity": "High",
                        "confidence_score": 0.99,
                        "start_line": idx,
                        "end_line": idx,
                        "affected_symbol": context.symbol_name,
                        "evidence": stripped,
                        "technical_explanation": (
                            "Division by literal zero throws ZeroDivisionError at runtime, halting execution."
                        ),
                        "potential_impact": "Unhandled runtime crash causing service unavailability.",
                        "suggested_fix": "Ensure divisor is checked for zero before division.",
                        "cwe_id": "CWE-369",
                    }
                )

            # 5. Null / None Dereference Pattern
            if re.search(r'if\s+\w+\s+is\s+None:\s*\w+\.\w+', line) or re.search(r'val\s*=\s*None;\s*val\.\w+', line):
                issues.append(
                    {
                        "issue_title": "Null / None Pointer Dereference",
                        "issue_description": "Attribute access on an object that is known or verified to be None.",
                        "category": "logic_bug",
                        "subcategory": "null_dereference",
                        "severity": "High",
                        "confidence_score": 0.95,
                        "start_line": idx,
                        "end_line": idx,
                        "affected_symbol": context.symbol_name,
                        "evidence": stripped,
                        "technical_explanation": (
                            "Accessing attributes on None causes AttributeError at runtime."
                        ),
                        "potential_impact": "Application crash and unexpected HTTP 500 error responses.",
                        "suggested_fix": "Guard with an appropriate condition or use optional chaining / default object.",
                        "cwe_id": "CWE-476",
                    }
                )

        # 6. Code Smell: Deep Nesting or High Complexity
        indent_levels = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
        if indent_levels and max(indent_levels) >= 16:
            deepest_line = max((idx for idx, line in enumerate(lines, start=start_offset) if len(line) - len(line.lstrip()) >= 16), default=start_offset)
            issues.append(
                {
                    "issue_title": "Deeply Nested Conditional Logic",
                    "issue_description": "Control flow contains 4+ levels of nested branching blocks.",
                    "category": "code_smell",
                    "subcategory": "cognitive_complexity",
                    "severity": "Low",
                    "confidence_score": 0.85,
                    "start_line": start_offset,
                    "end_line": deepest_line,
                    "affected_symbol": context.symbol_name,
                    "evidence": lines[deepest_line - start_offset].strip() if deepest_line - start_offset < len(lines) else "",
                    "technical_explanation": (
                        "Deeply nested control structures significantly impair readability and increase the risk "
                        "of missed edge-cases during maintenance."
                    ),
                    "potential_impact": "High defect rate and increased difficulty for code reviews.",
                    "suggested_fix": "Refactor nested branches using early return guards or helper methods.",
                    "cwe_id": "CWE-1120",
                }
            )

        return issues


def get_code_analyzer() -> BaseCodeAnalyzer:
    """Factory creating the configured code analyzer."""
    provider_type = settings.AI_ANALYSIS_PROVIDER.lower().strip()
    if provider_type == "mock":
        return MockCodeAnalyzer()

    if not settings.is_gemini_configured:
        logger.info(
            "AI Code Analysis configured for '%s', but GEMINI_API_KEY is not set. Operating in Offline Mode (MockCodeAnalyzer).",
            provider_type,
        )
        return MockCodeAnalyzer()

    return GeminiCodeAnalyzer(
        api_key=settings.GEMINI_API_KEY,
        model_name=settings.AI_ANALYSIS_MODEL,
        max_retries=settings.ANALYSIS_MAX_RETRIES,
        timeout=settings.gemini_request_timeout,
    )
