import os
import json
import time
from typing import Optional, Callable
from openai import OpenAI, APITimeoutError, APIConnectionError, InternalServerError, RateLimitError
from logger import logger

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "")),
            base_url=os.getenv("LLM_BASE_URL"),
        )
    return _client


MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")


# Errors worth retrying once — transient infrastructure issues
_RETRYABLE = (APITimeoutError, APIConnectionError, InternalServerError, RateLimitError)


def _do_llm_call(client: OpenAI, **kwargs) -> object:
    """
    Single attempt at a chat completion. Separated so the retry wrapper can call it twice.
    If retry also fails, callers should fall back to a safe static response.
    # Future: if both attempts fail, route through OpenRouter with a fallback model
    # (e.g. gemini-flash → gpt-4o-mini) to survive provider outages at runtime.
    """
    return client.chat.completions.create(**kwargs)


def extract_and_respond(
    system_prompt: str,
    conversation_history: list[dict],
    user_input: str,
    tools: Optional[list] = None,
    tool_handler: Optional[Callable[[str, dict], str]] = None,
) -> dict:
    """
    Single LLM call returning extracted structured data and a user-facing response.
    Optionally supports tool calling — if the LLM calls a tool, the handler is invoked
    and the result is fed back before getting the final JSON response.
    Retries once on transient errors (timeout, connection error, rate limit, 5xx).
    """
    messages = [
        {"role": "system", "content": system_prompt},
        *conversation_history,
        {"role": "user", "content": user_input},
    ]

    client = get_client()
    logger.debug(f"LLM call | model={MODEL} | history_turns={len(conversation_history) // 2}")

    kwargs = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.1,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    else:
        kwargs["response_format"] = {"type": "json_object"}

    for attempt in range(2):
        try:
            completion = _do_llm_call(client, **kwargs)
            break
        except _RETRYABLE as e:
            if attempt == 0:
                logger.warning(f"LLM transient error (attempt 1), retrying in 1s | {e}")
                time.sleep(1)
            else:
                logger.error(f"LLM transient error (attempt 2), giving up | {e}")
                raise

    response_msg = completion.choices[0].message

    # Handle tool calls if any
    if tools and response_msg.tool_calls:
        messages.append(response_msg)
        for tool_call in response_msg.tool_calls:
            args = json.loads(tool_call.function.arguments)
            logger.debug(f"tool_call | {tool_call.function.name} | args={args}")
            result = tool_handler(tool_call.function.name, args) if tool_handler else "ok"
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

        # Follow-up call to get the actual JSON response after tool use
        logger.debug("LLM follow-up call after tool use")
        for attempt in range(2):
            try:
                completion = _do_llm_call(
                    client,
                    model=MODEL,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.1,
                )
                break
            except _RETRYABLE as e:
                if attempt == 0:
                    logger.warning(f"LLM follow-up transient error (attempt 1), retrying in 1s | {e}")
                    time.sleep(1)
                else:
                    logger.error(f"LLM follow-up transient error (attempt 2), giving up | {e}")
                    raise
        response_msg = completion.choices[0].message

    raw = response_msg.content
    logger.debug(f"LLM response: {raw[:200]}{'...' if len(raw) > 200 else ''}")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.error(f"LLM returned non-JSON: {raw}")
        raise ValueError(f"LLM returned non-JSON: {raw}")
