import json
import requests
import time
from typing import Any
from phone_agent.actions.handler import do, finish
from phone_agent.config.tools import GEMINI_TOOLS

# Mapping of Gemini Tool Calls to internal actions
def map_gemini_to_internal(name: str, args: dict) -> dict:
    if name == "finish":
        return finish(**args)
    
    # Internal ActionHandler uses spaces for these names, but Gemini uses underscores
    internal_name = name.replace("_", " ") if name in ["Long_Press", "Double_Tap"] else name
    
    return do(action=internal_name, **args)

def gemini_request(config, messages: list[dict[str, Any]], start_time: float):
    """Handle Gemini Native API request."""
    # Convert OpenAI format to Gemini Native format
    contents = []
    system_instruction = None

    for msg in messages:
        role = msg["role"]
        content = msg.get("content")
        
        parts = []
        if isinstance(content, str) and content.strip():
            parts.append({"text": content})
        elif isinstance(content, list):
            for item in content:
                if item["type"] == "text":
                    parts.append({"text": item["text"]})
                elif item["type"] == "image_url":
                    url = item["image_url"]["url"]
                    if url.startswith("data:"):
                        header, data = url.split(",", 1)
                        mime_type = header.split(";")[0].split(":")[1]
                        parts.append({
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": data
                            }
                        })
        
        # 1. Handle Tool Calls in Assistant history
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments", "{}"))
                except:
                    args = {}
                parts.append({
                    "functionCall": {
                        "name": fn.get("name"),
                        "args": args
                    }
                })

        # 2. Handle Tool Responses (Results) in history
        if role == "tool":
            try:
                res_content = json.loads(msg.get("content", "{}"))
            except:
                res_content = {"result": msg.get("content")}
            contents.append({
                "role": "user", # Gemini expects functionResponse from user role
                "parts": [{
                    "functionResponse": {
                        "name": msg.get("name"),
                        "response": res_content
                    }
                }]
            })
            continue

        # Add thought signature if present (Crucial for Gemini 3)
        extra = msg.get("extra_content")
        if extra and isinstance(extra, dict):
            google_extra = extra.get("google")
            if google_extra and isinstance(google_extra, dict):
                sig = google_extra.get("thought_signature")
                if sig and parts:
                    parts[0]["thought_signature"] = sig

        if role == "system":
            system_instruction = {"parts": parts}
        else:
            gemini_role = "user" if role == "user" else "model"
            contents.append({"role": gemini_role, "parts": parts})

    # Prepare URL and Headers
    base = config.base_url.rstrip("/")
    # Gemini Native uses streamGenerateContent for streaming
    url = f"{base}/models/{config.model_name}:streamGenerateContent?alt=sse"
    
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": config.api_key
    }
    
    payload = {
        "contents": contents,
        "tools": GEMINI_TOOLS,
        "generationConfig": {
            "maxOutputTokens": config.max_tokens,
            "temperature": config.temperature,
            "topP": config.top_p,
            "candidateCount": 1,
        }
    }
    if system_instruction:
        payload["systemInstruction"] = system_instruction
    
    # Merge extra_body into generationConfig if any
    if config.extra_body:
        payload["generationConfig"].update(config.extra_body)

    response = requests.post(url, headers=headers, json=payload, stream=True)
    response.raise_for_status()

    raw_content = ""
    thought_signature = None
    structured_action = None
    tool_call_id = None
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
        try:
            chunk = json.loads(data_str)
        except json.JSONDecodeError:
            continue
        
        # Gemini native stream response has 'candidates'
        if not chunk.get("candidates"):
            continue
        
        candidate = chunk["candidates"][0]
        content_obj = candidate.get("content", {})
        parts = content_obj.get("parts", [])
        
        for part in parts:
            # Extract thought signature
            sig = part.get("thoughtSignature")
            if sig:
                thought_signature = sig
                
            # Handle Thinking/Thought parts (for Thinking models)
            thought = part.get("thought")
            if thought:
                # Treat thought as thinking text
                raw_content += thought
                
                if not first_token_received:
                    time_to_first_token = time.time() - start_time
                    first_token_received = True
                
                if not in_action_phase:
                    buffer += thought
                    # Check for markers in thought (though unlikely)
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
                    
                    if not marker_found:
                        # Print thought buffer if not entering action
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

            # Handle native Tool Calls
            if "functionCall" in part:
                fc = part["functionCall"]
                # Capture tool_call_id if provided by the API
                tool_call_id = fc.get("id")
                structured_action = map_gemini_to_internal(fc["name"], fc.get("args", {}))
                
                if not in_action_phase:
                    in_action_phase = True
                    print() # New line after thinking
                    if time_to_thinking_end is None:
                        time_to_thinking_end = time.time() - start_time

            if "text" in part:
                text = part["text"]
                raw_content += text
                
                if not first_token_received:
                    time_to_first_token = time.time() - start_time
                    first_token_received = True
                
                if in_action_phase:
                    continue
                
                buffer += text
                
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

    return raw_content, thought_signature, time_to_first_token, time_to_thinking_end, structured_action, tool_call_id
