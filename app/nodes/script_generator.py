from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types
from ..models.generation import ScriptGeneratorOutput
from ..config import settings

script_generator = Agent(
    name="script_generator",
    model=settings.model_coding,
    include_contents='none',
    instruction=(
        "You are an expert Python developer. Your task is to generate the calculation script.\n\n"
        "=== BLUEPRINT ===\n"
        "{blueprint}\n"
        "=================\n\n"
        "=== SCRIPT VALIDATION ERROR ===\n"
        "{script_validation_error?}\n"
        "===============================\n\n"
        "=== SCRIPT JUDGE FEEDBACK ===\n"
        "{script_judge_feedback?}\n"
        "=============================\n\n"
        "=== PREVIOUS SCRIPT ===\n"
        "{generated_script?}\n"
        "=======================\n\n"
        "INSTRUCTIONS:\n"
        "1. Generate the calculation script based strictly on the BLUEPRINT.\n"
        "2. The script must expose exactly one entrypoint function: `def calculate(inputs: dict) -> dict:`\n"
        "3. The keys extracted from `inputs` and returned in the result dict MUST exactly match the parameter names in the blueprint.\n"
        "4. You must STRICTLY implement the error_handling_strategy defined in the blueprint when invalid inputs are encountered.\n"
        "5. If a SCRIPT VALIDATION ERROR is present, it means your previous script failed syntax or structure checks. Fix it immediately.\n"
        "6. If SCRIPT JUDGE FEEDBACK is present, it means your script did not properly match the UI schema or blueprint. Follow the feedback to fix the script.\n"
        "7. You MUST aggressively cast all numerical inputs from the dictionary to float before performing math operations to prevent TypeError from string payloads.\n"
        "8. For any 'choice' parameters defined with `data_type: list`, the input dictionary will contain a list of strings (e.g., `[\"kg\"]`). You MUST extract the first element of the list before using it in your logic.\n"
        "9. You MUST include ALL keys defined as 'result' parameters in the blueprint in your final return dictionary on EVERY execution path (both success and error paths). To clear loading states on the frontend, you must always return a fallback value or empty state for all result fields even if an error occurs, or vice versa (e.g. returning `\"\"` for strings or `0` for numeric results on failure)."
    ),
    output_schema=ScriptGeneratorOutput,
    output_key="script_generator_output",
)
