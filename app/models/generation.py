from pydantic import BaseModel, Field

class GeneratedScript(BaseModel):
    script_content: str = Field(description="The complete, executable Python code for the calculator.")
    main_function_name: str = Field(description="The name of the main entrypoint function in the script.")

class ScriptGeneratorOutput(BaseModel):
    script_content: str = Field(description="The complete Python script.")

class ScriptJudgeOutput(BaseModel):
    verdict: str = Field(description="Must be exactly 'VALID' if script covers blueprint/schema, or 'INVALID' if flawed.")
    feedback: str = Field(default="", description="If verdict is INVALID, clear instructions for the script generator to fix the script.")

class CalculatorWorkflowState(BaseModel):
    # This represents the overall state of the workflow
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
