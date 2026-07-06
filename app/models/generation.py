"""Workflow Generation State Models.

This module defines the transient state structures used by the ADK workflow
during the generation process. These models track intermediate artifacts
like the generated script, validation errors, and LLM judge feedback.
"""

from pydantic import BaseModel, Field

class GeneratedScript(BaseModel):
    """Output structure expected from the Script Generator LLM."""
    script_content: str = Field(description="The complete, executable Python code for the calculator.")
    main_function_name: str = Field(description="The name of the main entrypoint function in the script.")

class ScriptGeneratorOutput(BaseModel):
    """Output structure expected from the Script Generator LLM."""
    script_content: str = Field(description="The complete Python script.")

class ScriptJudgeOutput(BaseModel):
    """Output structure expected from the Script Judge LLM."""
    verdict: str = Field(description="Must be exactly 'VALID' if script covers blueprint/schema, or 'INVALID' if flawed.")
    feedback: str = Field(default="", description="If verdict is INVALID, clear instructions for the script generator to fix the script.")

class CalculatorWorkflowState(BaseModel):
    """The central state object passed between nodes in the ADK graph.
    
    This acts as the shared memory for the generation pipeline, accumulating
    the original prompt, the blueprint, the generated code/UI, and any
    validation feedback from the judge.
    """
    user_prompt: str = ""
    blueprint: dict = Field(default_factory=dict)
    generated_script: dict = Field(default_factory=dict)
    script_validation_error: str = ""
    ui_validation_error: str = ""
    generation_retry_count: int = 0
    script_generator_output: dict = Field(default_factory=dict)
    script_judge_output: dict = Field(default_factory=dict)
    script_judge_feedback: str = ""
    calculator_id: str = ""
    a2ui_schema: list = Field(default_factory=list)
