import os
from typing import Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from google.adk.models.lite_llm import LiteLlm
from google.adk.models import Gemini
from google.genai import types

class EnvironmentLoader(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "local"

class BaseConfig(BaseSettings):    
    # Controls the maximum total number of generation retries allowed in a single agent run.
    # This is a shared counter that increments on ANY validation failure, including:
    # 1. Script validation failure (syntax/structure errors checked in the sandbox)
    # 2. UI schema validation failure (A2UI format Pydantic errors)
    # 3. Judge validation failure (LLM-as-a-judge static analysis rejection)
    # If the combined retries across all these steps exceed this number, the agent fails.
    max_generation_retries: int = 8
    
    # --- Model Configuration ---
    # The ADK supports Vertex AI models natively (e.g., "gemini-3.5-flash").
    # To use third-party models (OpenAI, Anthropic, OpenRouter, Groq), use LiteLlm.
    # IMPORTANT: You must expose the respective API keys in your environment variables
    # (or in your local .env file), for example: ANTHROPIC_API_KEY, OPENROUTER_API_KEY, etc.
    # 
    # NOTE ON GKE DEPLOYMENT: LiteLLM third-party models ONLY work locally out of the box.
    # They will fail on a GKE deployment because API keys are not injected into the GKE
    # environment by default. If you need third-party models on GKE, you must configure
    # GKE secrets or Google Cloud Secret Manager integration.
    # 
    # Example for Anthropic & OpenRouter:
    # model_reasoning: Any = LiteLlm(model="openrouter/deepseek/deepseek-v4-flash")
    # model_coding: Any = LiteLlm(model="anthropic/claude-sonnet-4-6")
    #
    # Resources:
    # - Google Models Pricing: https://ai.google.dev/gemini-api/docs/pricing
    # - LiteLLM Providers & Models: https://docs.litellm.ai/docs/providers
    
    model_reasoning: Any = Gemini(
        model="gemini-3.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3)
    )
    model_coding: Any = Gemini(
        model="gemini-3.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3)
    )
    model_script_judge: Any = Gemini(
        model="gemini-3.1-flash-lite",
        retry_options=types.HttpRetryOptions(attempts=3)
    )

class LocalConfig(BaseConfig):
    # --- Observability ---
    trace_enabled: bool = True
    trace_payloads: bool = True
    
    # Check if the python sandbox executor is working and configured properly on the server 
    # (e.g. on GKE) by running a minimal script (`print('ok')`) in it before starting a workflow.
    # If it fails, the workflow aborts immediately with an error.
    check_sandbox_on_start: bool = False
    
    # When True, disables the gVisor sandbox runtime class and tolerations on GKE. 
    # This allows the code executor to run on standard e2 nodes, bypassing GCE quota 
    # limitations for N2/N2D instances (which are required for gVisor).
    sandbox_bypass_gvisor: bool = True

class GkeConfig(BaseConfig):
    # --- Observability ---
    trace_enabled: bool = True
    trace_payloads: bool = True
    
    # Check if the python sandbox executor is working and configured properly on the server 
    # (e.g. on GKE) by running a minimal script (`print('ok')`) in it before starting a workflow.
    # If it fails, the workflow aborts immediately with an error.
    check_sandbox_on_start: bool = False
    
    # When True, disables the gVisor sandbox runtime class and tolerations on GKE. 
    # This allows the code executor to run on standard e2 nodes, bypassing GCE quota 
    # limitations for N2/N2D instances (which are required for gVisor).
    sandbox_bypass_gvisor: bool = True

env_loader = EnvironmentLoader()

if env_loader.environment == "gke":
    settings = GkeConfig()
else:
    settings = LocalConfig()
