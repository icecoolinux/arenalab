"""
LLM integration utilities for plugins (Anthropic and OpenAI).
"""

import os
import json
import logging
from typing import Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from plugins.core.api import PluginAPI

logger = logging.getLogger(__name__)


def is_llm_available(api: 'PluginAPI') -> bool:
    """
    Check if LLM is available (API keys configured).

    Args:
        api: PluginAPI instance

    Returns:
        True if API keys are configured in database or environment
    """
    from db import settings

    # Check database first, fall back to environment
    db_settings = settings.get_global_settings()
    return bool(
        db_settings.get("anthropic_api_key") or
        db_settings.get("openai_api_key") or
        os.environ.get("ANTHROPIC_API_KEY") or
        os.environ.get("OPENAI_API_KEY")
    )


def llm(api: 'PluginAPI', prompt: str, context_data: Optional[Dict[str, Any]] = None) -> str:
    """
    Query LLM with a prompt and optional context data.

    Args:
        api: PluginAPI instance
        prompt: The prompt/question to send to the LLM
        context_data: Optional dictionary of context data to include in the prompt

    Returns:
        LLM response text

    Raises:
        RuntimeError: If LLM is not available or API call fails
    """
    if not is_llm_available(api):
        raise RuntimeError(
            "LLM not available. Configure API keys in Settings page."
        )

    # Get API keys and provider preference from database first, fall back to environment
    from db import settings
    db_settings = settings.get_global_settings()

    # Get preferred provider (default to openai if not set)
    llm_provider = db_settings.get("llm_provider", "openai")

    # Prepare full prompt with context if provided
    full_prompt = prompt
    if context_data:
        context_str = json.dumps(context_data, indent=2, default=str)
        full_prompt = f"{prompt}\n\nContext Data:\n```json\n{context_str}\n```"
    print(full_prompt)

    # Get API keys
    anthropic_key = db_settings.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")
    openai_key = db_settings.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")

    # Define provider call functions
    def call_anthropic():
        if not anthropic_key:
            return None
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)

            # Get model from settings, default to claude-3-5-sonnet-20241022
            anthropic_model = db_settings.get("anthropic_model") or "claude-3-5-sonnet-20241022"

            response = client.messages.create(
                model=anthropic_model,
                max_tokens=2048,
                messages=[
                    {"role": "user", "content": full_prompt}
                ]
            )

            # Log usage to database
            from db import llm_usage
            llm_usage.log_usage(
                provider="anthropic",
                model=response.model,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
                context={
                    "plugin_name": api.context.plugin_name,
                    "scope": api.context.scope,
                    "target_id": api.context.target_id
                }
            )

            return response.content[0].text

        except ImportError:
            logger.warning("anthropic library not installed. Install with: pip install anthropic")
            return None
        except Exception as e:
            logger.error(f"Error calling Anthropic API: {e}")
            raise RuntimeError(f"Anthropic API error: {e}")

    def call_openai():
        if not openai_key:
            return None
        try:
            import openai
            client = openai.OpenAI(api_key=openai_key)

            # Get model from settings, default to gpt-4o-mini
            openai_model = db_settings.get("openai_model") or "gpt-4o-mini"

            response = client.chat.completions.create(
                model=openai_model,
                messages=[
                    {"role": "user", "content": full_prompt}
                ]
            )

            # Log usage to database
            from db import llm_usage
            usage_details = {}
            if hasattr(response.usage, 'completion_tokens_details') and response.usage.completion_tokens_details:
                usage_details["reasoning_tokens"] = getattr(response.usage.completion_tokens_details, 'reasoning_tokens', 0)

            llm_usage.log_usage(
                provider="openai",
                model=response.model,
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
                context={
                    "plugin_name": api.context.plugin_name,
                    "scope": api.context.scope,
                    "target_id": api.context.target_id
                },
                usage_details=usage_details
            )

            return response.choices[0].message.content

        except ImportError:
            logger.warning("openai library not installed. Install with: pip install openai")
            return None
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {e}")
            raise RuntimeError(f"OpenAI API error: {e}")

    # Call providers based on preference
    if llm_provider == "anthropic":
        # Try Anthropic first, fall back to OpenAI if not available
        result = call_anthropic()
        if result is not None:
            return result
        result = call_openai()
        if result is not None:
            return result
    else:
        # Try OpenAI first, fall back to Anthropic if not available
        result = call_openai()
        if result is not None:
            return result
        result = call_anthropic()
        if result is not None:
            return result

    raise RuntimeError("No LLM library available. Install with: pip install anthropic or pip install openai")
