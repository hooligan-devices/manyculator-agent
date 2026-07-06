"""Blueprint Generator — the FIRST Agent Node in the Manyculator workflow graph.

This is the most critical node in the entire system. It receives the user's
raw natural-language prompt and produces a ``CalculatorBlueprint`` — a structured
Pydantic model that becomes the **single source of truth** consumed by every
downstream node (script_generator, ui_schema_generator, script_judge, etc.).

Dual purpose — intent routing:
    The ``CalculatorBlueprint.is_calculator`` flag doubles as the intent signal.
    If the user's prompt is *not* about building a calculator (e.g. "tell me a
    joke"), the LLM sets ``is_calculator=False``, and the downstream
    ``intent_router`` function node short-circuits the workflow with a polite
    rejection. This keeps intent classification co-located with blueprint
    generation so the model only needs a single inference call.

Output storage:
    ``output_key="blueprint"`` causes ADK to store the structured output in
    ``ctx.state['blueprint']`` so that every subsequent node can access it via
    ``state['blueprint']`` without explicit parameter passing.
"""

from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types
from ..models.blueprint import CalculatorBlueprint
from ..config import settings

# ---------------------------------------------------------------------------
# Blueprint Generator Agent Node
# ---------------------------------------------------------------------------
# ADK will invoke the model specified by `settings.model_reasoning`,
# feed it the `instruction` prompt plus the user's message, and parse the
# response into the `output_schema` (CalculatorBlueprint).
# ---------------------------------------------------------------------------
blueprint_generator = Agent(
    name="blueprint_generator",

    # Uses the strongest available model because blueprint accuracy is the
    # single largest lever on end-to-end output quality. See config.py for
    # the concrete model identifier (default: gemini-3.5-flash).
    model=settings.model_reasoning,

    instruction=(
        "You are the Chief Architect for Manyculator. Your job is to analyze the user's request and create a comprehensive blueprint.\n\n"

        # -- Rule 1: STRICT MATHEMATICS & CONSTANTS --
        # WHY: The script_generator LLM sometimes invents its own constants
        # (e.g. using 2.205 instead of 2.20462 for kg→lbs). By forcing the
        # blueprint to pin every constant with exact values, the downstream
        # script_generator has an unambiguous spec to follow, and the
        # script_judge can verify compliance.
        "1. STRICT MATHEMATICS & CONSTANTS:\n"
        "   - You MUST explicitly declare all constants and conversion factors in `computation_logic` (e.g., 'Use exactly 0.453592 for lbs to kg').\n"
        "   - You MUST explicitly state rounding rules (e.g., 'Round all final outputs to 2 decimal places using standard Python round()').\n\n"

        # -- Rule 2: ERROR HANDLING CONTRACT --
        # WHY: The generated Python script and the UI schema must agree on the
        # exact shape of error responses. If the script returns {"err": "..."}
        # but the UI expects {"error": "..."}, the error will silently vanish.
        # Pinning the exact dict structure in the blueprint creates a binding
        # contract between script_generator and ui_schema_generator.
        "2. ERROR HANDLING CONTRACT:\n"
        "   - Define the EXACT structure of error dictionaries (e.g., `{'error': 'Invalid Input: Height must be > 0'}`). The script MUST use these exact keys and message substrings.\n\n"

        # -- Rule 3: LIMIT VALUE RANGES --
        # WHY: Users sometimes specify explicit ranges in their prompt or in an
        # attached image/table (e.g. "age: 18-65"). If the blueprint invents
        # wider ranges, the generated Slider/TextField validation will be wrong.
        # Conversely, inventing ranges when the user didn't specify any leads to
        # unexpectedly restrictive calculators.
        "3. LIMIT VALUE RANGES:\n"
        "   - If user provided ranges for input values (in prompt, image or table), you MUST set corresponding min and max values. DO NOT set ranges more, than provided. \n\n"

        # -- Rule 4: PARAMETER DEFINITION STRICTNESS (A2UI PROTOCOL) --
        # WHY: The A2UI cross-platform protocol requires exact component_type
        # strings ("TextField", "ChoicePicker", "Slider", "CheckBox", "Result")
        # to render the correct native widget on iOS/Android/Web. Typos or
        # free-form names (e.g. "dropdown") will cause the UI to fall back to
        # a plain text input or crash entirely.
        #
        # CRITICAL SUBTLETY — ChoicePicker array semantics:
        # A2UI's ChoicePicker ALWAYS submits its value as a JSON array, even
        # when is_multi=false (e.g. ["kg"] not "kg"). If the blueprint's
        # computation_logic says "if unit == 'kg'" instead of
        # "if unit[0] == 'kg'", the generated script will have a subtle bug
        # that passes syntax validation but fails at runtime. This rule forces
        # the blueprint to explicitly warn about array unwrapping so the
        # script_generator handles it correctly.
        "4. PARAMETER DEFINITION STRICTNESS (A2UI PROTOCOL):\n"
        "   - You MUST classify parameters using the exact `component_type` (e.g., 'TextField', 'ChoicePicker', 'Slider', 'CheckBox', 'Result').\n"
        "   - Example of a ChoicePicker parameter: `{\"name\": \"weight_unit\", \"kind\": \"input\", \"component_type\": \"ChoicePicker\", \"options\": [{\"label\": \"Kilograms\", \"value\": \"kg\"}], \"is_multi\": false}`\n"
        "   - Example of a TextField parameter: `{\"name\": \"weight\", \"kind\": \"input\", \"component_type\": \"TextField\", \"keyboard_type\": \"number\"}`\n"
        "   - Example of a Result parameter: `{\"name\": \"bmi_value\", \"kind\": \"result\", \"component_type\": \"Result\", \"data_type\": \"number\"}`\n"
        "   - CRITICAL: A2UI `ChoicePicker` components ALWAYS submit their values as an array (e.g., `[\"kg\"]`), even for single selections (`is_multi: false`). Therefore, your `computation_logic` must expect array inputs for these components.\n"

        # -- Rule 5: OUTPUT DICTIONARY KEYS --
        # WHY: The persist_and_respond node maps script output dict keys to
        # A2UI Result components by matching on the `name` field. If the script
        # returns {"bmi": 22.5} but the Result parameter is named "bmi_value",
        # the result will never appear in the UI. This rule prevents that
        # mismatch at the blueprint level so both script_generator and
        # ui_schema_generator work from identical names.
        "5. OUTPUT DICTIONARY KEYS:\n"
        "   - The final output dictionary of the Python script MUST use keys that exactly match the `name` properties of your 'result' parameters.\n"
    ),

    # Force the LLM output into the CalculatorBlueprint Pydantic schema.
    # ADK handles JSON extraction and validation automatically; if the LLM
    # produces malformed output, ADK will retry with the validation error
    # appended to the prompt (up to the configured retry limit).
    output_schema=CalculatorBlueprint,

    # Store the parsed blueprint in workflow state under the key "blueprint"
    # (i.e. ctx.state["blueprint"]), making it available to all downstream
    # nodes without explicit wiring: script_generator reads computation_logic,
    # ui_schema_generator reads parameters, script_judge reads edge_cases, etc.
    output_key="blueprint",
)

