import json
import requests
import time
from typing import Any

def openai_request(config, messages: list[dict[str, Any]], start_time: float):
    """Handle OpenAI-compatible API request."""
    url = f"{config.base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.api_key}",
    }
    payload = {
        "model": config.model_name,
        "messages": messages,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "top_p": config.top_p,
        "frequency_penalty": config.frequency_penalty,
        "stream": True,
        **config.extra_body,
    }

    response = requests.post(url, headers=headers, json=payload, stream=True)
    response.raise_for_status()

    raw_content = ""
    thought_signature = None
    buffer = ""
    action_markers = ["finish(message=", "do(action="]
    in_action_phase = False
    first_token_received = False
    time_to_first_token = None
    time_to_thinking_end = None

    for line in response.iter_lines():
        if not line:
            continue

        line = line.decode("utf-8")
        if not line.startswith("data: "):
            continue

        data_str = line[6:].strip()
        if data_str == "[DONE]":
            break

        try:
            chunk = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        if not chunk.get("choices"):
            continue

        delta = chunk["choices"][0].get("delta", {})

        # Extract thought signature for OpenAI compatibility mode (e.g. via OpenRouter/Google Proxy)
        extra = delta.get("extra_content")
        if extra and isinstance(extra, dict):
            google_extra = extra.get("google")
            if google_extra and isinstance(google_extra, dict):
                sig = google_extra.get("thought_signature")
                if sig:
                    thought_signature = sig

        if delta.get("content") is not None:
            content = delta["content"]
            raw_content += content

            if not first_token_received:
                time_to_first_token = time.time() - start_time
                first_token_received = True

            if in_action_phase:
                continue

            buffer += content

            marker_found = False
            for marker in action_markers:
                if marker in buffer:
                    thinking_part = buffer.split(marker, 1)[0]
                    print(thinking_part, end="", flush=True)
                    print()
                    in_action_phase = True
                    marker_found = True
                    if time_to_thinking_end is None:
                        time_to_thinking_end = time.time() - start_time
                    break

            if marker_found:
                continue

            is_potential_marker = False
            for marker in action_markers:
                for i in range(1, len(marker)):
                    if buffer.endswith(marker[:i]):
                        is_potential_marker = True
                        break
                if is_potential_marker:
                    break

            if not is_potential_marker:
                print(buffer, end="", flush=True)
                buffer = ""

    return raw_content, thought_signature, time_to_first_token, time_to_thinking_end
