from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types
from ..config import settings
from ..models.generation import ScriptJudgeOutput

def script_judge_instruction(ctx):
    blueprint = ctx.state.get("blueprint", "")
    if hasattr(blueprint, "model_dump_json"):
        blueprint = blueprint.model_dump_json()
    else:
        blueprint = str(blueprint)
        
    script_output = ctx.state.get("script_generator_output", {})
    if isinstance(script_output, dict):
        script_content = script_output.get("script_content", "")
    elif hasattr(script_output, "script_content"):
        script_content = script_output.script_content
    else:
        script_content = str(script_output)
        
    # Get schema from validator node input if available, or from state
    a2ui_schema = ctx.state.get("a2ui_schema", "Schema not generated yet")
    if isinstance(a2ui_schema, list) or isinstance(a2ui_schema, dict):
        import json
        a2ui_schema = json.dumps(a2ui_schema, indent=2)
        
    return f"""You are an expert Python judge and architect.
    
    You must evaluate the generated python script to ensure it correctly implements the provided blueprint and integrates perfectly with the provided UI schema.
    
    ### Blueprint
    ```json
    {blueprint}
    ```
    
    ### UI Schema (A2UI)
    ```json
    {a2ui_schema}
    ```
    
    ### Generated Python Script
    ```python
    {script_content}
    ```
    
    Check the following three criteria:
    1. Does the script fully reflect the blueprint and completely cover it? (Does it do what it's supposed to do?)
    2. Does the script perfectly match the UI schema? The `calculate(inputs)` function MUST correctly extract the inputs exactly as defined in the UI schema bindings, and its return dictionary MUST exactly match the paths expected by the output text elements in the schema.
    3. Does the script include ALL output keys defined in the schema in its return dictionary on EVERY execution path (both success and error cases)? If the script returns early due to an error, it MUST still return fallback values for all expected output keys to resolve frontend loading states (e.g. returning `\"\"` for strings or `0` for numeric fields on failure).
    
    If ALL THREE criteria are met, return 'VALID' as your verdict.
    If ANY criteria fails, return 'INVALID' and provide extremely clear feedback on what is wrong and exactly how the script generator should fix it in the next iteration.
    """

script_judge = Agent(
    name="script_judge",
    model=settings.model_script_judge,
    instruction=script_judge_instruction,
    output_schema=ScriptJudgeOutput,
)
