"""Calculator Database Entities and Types.

This module defines the core database models, enums, and components
that represent a finalized calculator. These models map directly to
Firestore documents and enforce strict typing on the UI parameters.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional, Dict, Literal, Union, Annotated
from pydantic import BaseModel, Field

class CalculatorStatus(str, Enum):
    """Lifecycle status of a generated calculator."""
    DRAFT = "draft"
    ACTIVE = "active"
    ERROR = "error"
    ARCHIVED = "archived"

class ParameterKind(str, Enum):
    """Defines the operational role of a parameter within the calculator."""
    INPUT = "input"           # User-controllable via UI (TextField, Slider, etc.)
    RESULT = "result"         # Computed output, displayed to user
    INITIAL = "initial"       # Hardcoded constant, never changes
    DERIVED = "derived"       # Intermediate computed value, not shown to user
    CHOICE = "choice"         # Constrained selection from options (dropdown/radio)

class ValidationRules(BaseModel):
    """Numerical or pattern validation constraints for UI components."""
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step: Optional[float] = None
    required: bool = True
    pattern: Optional[str] = None       # Regex for string validation

class UIComponent(str, Enum):
    """Supported frontend UI component types."""
    TEXT_FIELD = "TextField"
    CHOICE_PICKER = "ChoicePicker"
    SLIDER = "Slider"
    CHECK_BOX = "CheckBox"
    RESULT = "Result"

class ChoiceOption(BaseModel):
    """A selectable option within a ChoicePicker component."""
    label: str
    value: str

class ParameterDef(BaseModel):
    """Definition of a single UI or logical parameter used by the calculator.
    
    This schema dictates how the A2UI generator should render the frontend
    component, and what data types the Python script should expect as input.
    """
    name: str
    kind: ParameterKind
    component_type: Literal["TextField", "ChoicePicker", "Slider", "CheckBox", "Result"]
    
    # TextField Properties
    keyboard_type: Optional[Literal["text", "number"]] = Field(default=None, description="Only for TextField")
    validation: Optional[ValidationRules] = None
    
    # ChoicePicker Properties
    options: Optional[List[ChoiceOption]] = Field(default=None, description="Required for ChoicePicker. List of allowed options.")
    is_multi: Optional[bool] = Field(default=None, description="For ChoicePicker. Always false for single-select, but ChoicePicker output is always an array.")
    
    # Slider Properties
    min_value: Optional[float] = Field(default=None, description="Min value for Slider")
    max_value: Optional[float] = Field(default=None, description="Max value for Slider")
    step: Optional[float] = Field(default=None, description="Step for Slider")
    
    # Result Properties
    data_type: Optional[Literal["number", "string", "boolean", "list"]] = Field(default=None, description="Only for Result")

class CalculatorDefinition(BaseModel):
    """Core entity representing a fully generated calculator.
    
    This is the exact structure saved to the persistent database (e.g. Firestore).
    It contains both the declarative A2UI schema needed by the frontend and
    the raw Python logic script needed by the sandbox executor.
    """
    id: str                          # UUID
    name: str                        # Human-readable name
    description: str                 # Generated description for user
    created_at: datetime
    updated_at: datetime
    status: CalculatorStatus         # DRAFT | ACTIVE | ERROR | ARCHIVED
    
    # Parameter definitions
    parameters: List[ParameterDef]
    
    # Generated artifacts
    script: str = ""                      # Python calculation script
    test_script: str = ""                 # pytest test suite
    a2ui_schema: Any = Field(default_factory=dict)  # A2UI declarative JSON (can be Dict for v0.8 or List for v0.9.1)
    
    original_prompt: str             # User's original intent
    
    # Config
    retry_count: int = 0             # How many retries were needed
    generation_model: str = ""       # Which Gemini model was used
