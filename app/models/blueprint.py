from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from .calculator import ParameterDef

class CalculatorBlueprint(BaseModel):
    is_calculator: bool = Field(description="True if the user's intent is to create a calculator or converter. False otherwise.")
    reasoning: str = Field(description="Brief reasoning for the classification.")
    calculator_name: str = Field(default="", description="Suggested name for the calculator.")
    calculator_description: str = Field(default="", description="Suggested brief description of what the calculator computes and how.")
    parameters: List[ParameterDef] = Field(default_factory=list, description="List of all parameters required for the calculator, including inputs and results. Must be exhaustive.")
    computation_logic: str = Field(default="", description="Detailed, step-by-step description of the mathematical logic or algorithm to implement.")
    edge_cases: List[str] = Field(default_factory=list, description="List of boundary conditions or invalid states to handle (e.g. division by zero, negative amounts).")
    error_handling_strategy: str = Field(default="", description="Explicit rule for what the output dictionary should look like when an error occurs (e.g., return {'error': 'message'}).")

