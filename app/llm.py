"""LLM interaction utilities.
This module encapsulates all OpenRouter/OpenAI interactions so the rest of the
application code (e.g., FastAPI routers) remains clean. It fetches the
system prompt from `prompt.py` and exposes `get_instruction()` to turn a
user voice command + current task list into a validated `LLMTaskInstruction`.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from openai import OpenAI
from loguru import logger

from .prompt import SYSTEM_PROMPT
from . import schemas  # local import to get Pydantic models

# Initialise the OpenRouter client (lazy single instance)
_openrouter_api_key: Optional[str] = os.getenv("OPENROUTER_API_KEY")
if not _openrouter_api_key:
    logger.warning("OPENROUTER_API_KEY not found. LLM functions are disabled.")
    _client: Optional[OpenAI] = None
else:
    _client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=_openrouter_api_key)


def is_configured() -> bool:
    """Return True if the OpenRouter client is ready for use."""
    return _client is not None


def get_instruction(transcribed_text: str, current_tasks_str: str) -> schemas.LLMTaskInstruction:
    """Call the LLM and return a validated `LLMTaskInstruction`.

    Parameters
    ----------
    transcribed_text: str
        The text obtained from speech recognition.
    current_tasks_str: str
        String representation of current tasks (one per line).
    """
    if not _client:
        raise RuntimeError("LLM client not configured. Set OPENROUTER_API_KEY.")

    user_prompt = (
        f"User's voice command: {transcribed_text}\n\nCurrent tasks:\n{current_tasks_str or 'No tasks currently exist.'}"
    )

    logger.info("Sending prompt to OpenRouter LLM ...")
    completion = _client.chat.completions.create(
        model="meta-llama/llama-4-maverick",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )

    llm_response = completion.choices[0].message.content
    logger.debug(f"LLM raw response: {llm_response}")

    try:
        instruction_data = json.loads(llm_response)
        instruction = schemas.LLMTaskInstruction(**instruction_data)
    except json.JSONDecodeError as exc:
        logger.error(f"Failed to decode LLM JSON: {exc}\nRaw: {llm_response}")
        raise
    except Exception as exc:
        logger.error(f"Error validating LLM response: {exc}\nRaw: {llm_response}")
        raise

    return instruction
