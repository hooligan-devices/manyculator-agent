import time
import json
import logging
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import BaseTool, ToolContext
from google.adk.events.event import Event
from google.adk.agents.invocation_context import InvocationContext
from app.config import settings

logger = logging.getLogger(__name__)

class TracePlugin(BasePlugin):
    """Local console logger for Agent trace visualization."""
    
    def __init__(self):
        super().__init__(name="trace_plugin")
        self._timings = {}

    async def before_agent_callback(self, *, agent, callback_context: CallbackContext) -> None:
        if not settings.trace_enabled:
            return
            
        agent_name = callback_context.agent_name
        invocation_id = callback_context.invocation_id
        
        # Store start time for this specific agent invocation
        self._timings[invocation_id] = time.perf_counter()
        
        logger.info(f"\n[TRACE] \033[94m▶ {agent_name} started\033[0m")

    async def after_agent_callback(self, *, agent, callback_context: CallbackContext) -> None:
        if not settings.trace_enabled:
            return
            
        agent_name = callback_context.agent_name
        invocation_id = callback_context.invocation_id
        
        start_time = self._timings.pop(invocation_id, time.perf_counter())
        elapsed = time.perf_counter() - start_time
        
        logger.info(f"\n[TRACE] \033[94m◀ {agent_name} completed\033[0m ({elapsed:.2f}s)")

    async def before_model_callback(self, *, callback_context: CallbackContext, llm_request: LlmRequest) -> None:
        if not settings.trace_enabled:
            return
            
        if settings.trace_payloads:
            try:
                if llm_request.contents:
                    last_msg = llm_request.contents[-1]
                    parts = []
                    for p in last_msg.parts:
                        if hasattr(p, "text") and p.text:
                            parts.append(p.text)
                        elif hasattr(p, "function_call") and p.function_call:
                            parts.append(f"ToolCall({p.function_call.name})")
                    content_str = " | ".join(parts)
                    logger.info(f"\n        [Payload IN ] {content_str[:500]}{'...' if len(content_str)>500 else ''}")
            except Exception:
                pass

    async def after_model_callback(self, *, callback_context: CallbackContext, llm_response: LlmResponse) -> None:
        if not settings.trace_enabled:
            return
            
        model = llm_response.model_version or "unknown"
        if "litellm:" in model:
            model = model.split(":")[-1]
            
        in_tokens = 0
        out_tokens = 0
        
        if hasattr(llm_response, "usage_metadata") and llm_response.usage_metadata:
            in_tokens = getattr(llm_response.usage_metadata, "prompt_token_count", 0)
            out_tokens = getattr(llm_response.usage_metadata, "candidates_token_count", 0)
            
        logger.info(f"\n[TRACE]   \033[90m├─ LLM call:\033[0m {model} | {in_tokens} in → {out_tokens} out tokens")
        
        if settings.trace_payloads:
            try:
                if llm_response.candidates and llm_response.candidates[0].content:
                    parts = []
                    for p in llm_response.candidates[0].content.parts:
                        if hasattr(p, "text") and p.text:
                            parts.append(p.text)
                        elif hasattr(p, "function_call") and p.function_call:
                            parts.append(f"ToolCall({p.function_call.name})")
                    content_str = " | ".join(parts)
                    logger.info(f"\n        [Payload OUT] {content_str[:500]}{'...' if len(content_str)>500 else ''}")
            except Exception:
                pass

    async def before_tool_callback(self, *, tool: BaseTool, tool_args: dict, tool_context: ToolContext) -> None:
        if not settings.trace_enabled:
            return
            
        tool_name = tool.name
        tool_call_id = id(tool_args)
        self._timings[f"tool_{tool_call_id}"] = time.perf_counter()
        
        if settings.trace_payloads:
            args_str = json.dumps(tool_args, default=str)
            logger.info(f"\n[TRACE]   \033[93m├─ Tool:\033[0m {tool_name} | IN: {args_str}")
        else:
            logger.info(f"\n[TRACE]   \033[93m├─ Tool:\033[0m {tool_name} started")

    async def after_tool_callback(self, *, tool: BaseTool, tool_args: dict, tool_context: ToolContext, result: dict) -> None:
        if not settings.trace_enabled:
            return
            
        tool_name = tool.name
        tool_call_id = id(tool_args)
        start_time = self._timings.pop(f"tool_{tool_call_id}", time.perf_counter())
        elapsed = time.perf_counter() - start_time
        
        if settings.trace_payloads:
            resp_str = json.dumps(result, default=str)[:500]
            logger.info(f"\n[TRACE]   \033[93m└─ Tool:\033[0m {tool_name} | OUT: {resp_str} ({elapsed:.2f}s)")
        else:
            summary = ""
            if isinstance(result, dict):
                if "passed" in result:
                    summary = f" | passed={result['passed']}"
                elif "status" in result:
                    summary = f" | status={result['status']}"
            
            logger.info(f"\n[TRACE]   \033[93m└─ Tool:\033[0m {tool_name} completed{summary} ({elapsed:.2f}s)")
