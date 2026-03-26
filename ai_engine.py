"""
FitAI — Multi-Model AI Engine with Fallback & Robust JSON Parsing
=================================================================
Implements:
- Try-Catch-Rotate across 7 free OpenRouter models
- Regex-based JSON extraction from mixed AI output
- json_repair for fixing malformed JSON
- Jitter delay between retries to avoid thundering herd
- Strict Mode system prompts
- Failed model logging
"""

import requests
import json
import re
import time
import random
import logging
import os
from json_repair import repair_json

logger = logging.getLogger("fitai.ai")

# ═══════════════════════════════════════
#  MODEL CONFIGURATION
# ═══════════════════════════════════════
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# Ordered by preference — best-quality first
MODEL_POOL = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "deepseek/deepseek-chat-v3-0324:free",
    "deepseek/deepseek-r1:free",
    "google/gemma-3-27b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "stepfun/step-3.5-flash:free",
    "arcee-ai/trinity-large-preview:free",
]

# Track failed models for monitoring
_failed_models = []

# ═══════════════════════════════════════
#  STRICT MODE SYSTEM PROMPT PREFIX
# ═══════════════════════════════════════
STRICT_JSON_PREFIX = (
    "CRITICAL INSTRUCTION: Output ONLY valid JSON. "
    "No markdown fences, no preamble, no commentary, no trailing text. "
    "Do NOT wrap output in ```json``` code blocks. "
    'If you cannot fulfill the request, return {"error": "reason"}. '
    "Begin your response with { and end with }.\n\n"
)


def get_failed_models():
    """Return list of recently failed model IDs for monitoring."""
    return list(_failed_models)


# ═══════════════════════════════════════
#  CORE: MULTI-MODEL AI CALL WITH FALLBACK
# ═══════════════════════════════════════
def call_ai(messages, system_prompt="", require_json=False, max_retries=None):
    """
    Call OpenRouter with multi-model fallback.

    Args:
        messages: List of {role, content} dicts
        system_prompt: System context for the AI
        require_json: If True, applies Strict Mode prefix
        max_retries: Max models to try (default: all)

    Returns:
        str: The AI response content (raw text)
        If all models fail, returns a JSON error string.
    """
    if max_retries is None:
        max_retries = len(MODEL_POOL)

    # Apply Strict Mode if JSON is required
    full_system = system_prompt
    if require_json:
        full_system = STRICT_JSON_PREFIX + system_prompt

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://fitai.app",
        "X-Title": "FitAI Workout Planner",
    }

    all_messages = []
    if full_system:
        all_messages.append({"role": "system", "content": full_system})
    all_messages.extend(messages)

    last_error = None

    for attempt, model_id in enumerate(MODEL_POOL[:max_retries]):
        payload = {
            "model": model_id,
            "messages": all_messages,
            "temperature": 0.7,
            "max_tokens": 3000,
        }

        try:
            # Jitter delay between retries (not on first attempt)
            if attempt > 0:
                jitter = random.uniform(0.1, 0.3)
                logger.info(f"Retry #{attempt}: switching to {model_id} (jitter={jitter:.2f}s)")
                time.sleep(jitter)

            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=90,
            )

            # Handle rate limit and server errors → rotate
            if response.status_code == 429:
                logger.warning(f"Model {model_id}: 429 Rate Limited")
                _failed_models.append({"model": model_id, "error": "429", "time": time.time()})
                last_error = f"Rate limited on {model_id}"
                continue

            if response.status_code >= 500:
                logger.warning(f"Model {model_id}: {response.status_code} Server Error")
                _failed_models.append({"model": model_id, "error": str(response.status_code), "time": time.time()})
                last_error = f"Server error {response.status_code} on {model_id}"
                continue

            response.raise_for_status()
            data = response.json()

            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                logger.warning(f"Model {model_id}: empty response")
                _failed_models.append({"model": model_id, "error": "empty", "time": time.time()})
                last_error = f"Empty response from {model_id}"
                continue

            logger.info(f"Success: {model_id} (attempt #{attempt + 1})")
            return content

        except requests.exceptions.Timeout:
            logger.warning(f"Model {model_id}: timeout")
            _failed_models.append({"model": model_id, "error": "timeout", "time": time.time()})
            last_error = f"Timeout on {model_id}"
            continue

        except requests.exceptions.RequestException as e:
            logger.warning(f"Model {model_id}: {e}")
            _failed_models.append({"model": model_id, "error": str(e), "time": time.time()})
            last_error = str(e)
            continue

    # All models failed
    logger.error(f"All {max_retries} models failed. Last error: {last_error}")
    return json.dumps({"error": f"All AI models unavailable. Last: {last_error}"})


# ═══════════════════════════════════════
#  JSON EXTRACTION & REPAIR
# ═══════════════════════════════════════
def extract_json(raw_response):
    """
    Robustly extract valid JSON from an AI response that may contain
    thinking tags, markdown fences, commentary, or malformed JSON.

    Stages:
    1. Strip <think>...</think> blocks
    2. Try direct parse (response is already valid JSON)
    3. Extract from ```json ... ``` fences
    4. Regex: find the outermost { ... } block
    5. Use json_repair as last resort

    Returns:
        dict | list: Parsed JSON object
    Raises:
        ValueError: If no valid JSON found after all strategies
    """
    if not raw_response or not isinstance(raw_response, str):
        raise ValueError("Empty or non-string AI response")

    text = raw_response.strip()

    # ── Stage 1: Strip thinking tags ──
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # ── Stage 2: Direct parse ──
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # ── Stage 3: Fenced JSON blocks ──
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            # Try repair on fenced content
            try:
                repaired = repair_json(fence_match.group(1).strip())
                return json.loads(repaired)
            except Exception:
                pass

    # ── Stage 4: Regex — outermost JSON object ──
    # Find the first { and last } to extract the JSON object
    brace_match = re.search(r"\{", text)
    if brace_match:
        start = brace_match.start()
        # Find matching closing brace by counting nesting
        depth = 0
        end = start
        in_string = False
        escape_next = False
        for i in range(start, len(text)):
            c = text[i]
            if escape_next:
                escape_next = False
                continue
            if c == "\\":
                escape_next = True
                continue
            if c == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break

        if depth == 0 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                # Try repair
                try:
                    repaired = repair_json(candidate)
                    return json.loads(repaired)
                except Exception:
                    pass

    # ── Stage 5: Array extraction ──
    bracket_match = re.search(r"\[", text)
    if bracket_match:
        start = bracket_match.start()
        depth = 0
        end = start
        in_string = False
        escape_next = False
        for i in range(start, len(text)):
            c = text[i]
            if escape_next:
                escape_next = False
                continue
            if c == "\\":
                escape_next = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if depth == 0 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                try:
                    repaired = repair_json(candidate)
                    return json.loads(repaired)
                except Exception:
                    pass

    # ── Stage 6: Full-text repair as last resort ──
    try:
        repaired = repair_json(text)
        result = json.loads(repaired)
        if isinstance(result, (dict, list)):
            return result
    except Exception:
        pass

    raise ValueError(f"Could not extract valid JSON from AI response (length={len(text)})")


def call_ai_json(messages, system_prompt=""):
    """
    Convenience: Call AI with Strict Mode and auto-parse the JSON response.
    Returns (parsed_dict, None) on success, or (None, error_string) on failure.
    """
    raw = call_ai(messages, system_prompt, require_json=True)
    try:
        parsed = extract_json(raw)
        return parsed, None
    except ValueError as e:
        logger.error(f"JSON extraction failed: {e}")
        return None, str(e)
