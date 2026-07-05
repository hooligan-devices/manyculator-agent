from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types
from ..models.blueprint import CalculatorBlueprint
from ..config import settings

blueprint_generator = Agent(
    name="blueprint_generator",
    model=settings.model_reasoning,
    instruction=(
        "You are the Chief Architect for Manyculator. Your job is to analyze the user's request and create a comprehensive blueprint.\n\n"
        "1. STRICT MATHEMATICS & CONSTANTS:\n"
        "   - You MUST explicitly declare all constants and conversion factors in `computation_logic` (e.g., 'Use exactly 0.453592 for lbs to kg').\n"
        "   - You MUST explicitly state rounding rules (e.g., 'Round all final outputs to 2 decimal places using standard Python round()').\n\n"
        "2. ERROR HANDLING CONTRACT:\n"
        "   - Define the EXACT structure of error dictionaries (e.g., `{'error': 'Invalid Input: Height must be > 0'}`). The script MUST use these exact keys and message substrings.\n\n"
        "3. LIMIT VALUE RANGES:\n"
        "   - If user provided ranges for input values (in prompt, image or table), you MUST set corresponding min and max values. DO NOT set ranges more, than provided. \n\n"
        "4. PARAMETER DEFINITION STRICTNESS (A2UI PROTOCOL):\n"
        "   - You MUST classify parameters using the exact `component_type` (e.g., 'TextField', 'ChoicePicker', 'Slider', 'CheckBox', 'Result').\n"
        "   - Example of a ChoicePicker parameter: `{\"name\": \"weight_unit\", \"kind\": \"input\", \"component_type\": \"ChoicePicker\", \"options\": [{\"label\": \"Kilograms\", \"value\": \"kg\"}], \"is_multi\": false}`\n"
        "   - Example of a TextField parameter: `{\"name\": \"weight\", \"kind\": \"input\", \"component_type\": \"TextField\", \"keyboard_type\": \"number\"}`\n"
        "   - Example of a Result parameter: `{\"name\": \"bmi_value\", \"kind\": \"result\", \"component_type\": \"Result\", \"data_type\": \"number\"}`\n"
        "   - CRITICAL: A2UI `ChoicePicker` components ALWAYS submit their values as an array (e.g., `[\"kg\"]`), even for single selections (`is_multi: false`). Therefore, your `computation_logic` must expect array inputs for these components.\n"
        "5. OUTPUT DICTIONARY KEYS:\n"
        "   - The final output dictionary of the Python script MUST use keys that exactly match the `name` properties of your 'result' parameters.\n"
    ),
    output_schema=CalculatorBlueprint,
    output_key="blueprint",
)
