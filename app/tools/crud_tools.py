from typing import Dict, Any, List
from ..calculator_store import store
from ..models.calculator import CalculatorStatus

def get_calculator(calculator_id: str) -> Dict[str, Any]:
    """Retrieve an existing calculator definition and its A2UI schema.
    
    Args:
        calculator_id: The UUID of the calculator to retrieve.
    """
    calc = store.get(calculator_id)
    if not calc:
        return {"error": f"Calculator with ID {calculator_id} not found."}
    
    return {
        "id": calc.id,
        "name": calc.name,
        "description": calc.description,
        "status": calc.status.value,
        "parameters": [p.model_dump() for p in calc.parameters],
        "a2ui_schema": calc.a2ui_schema,
    }

def delete_calculator(calculator_id: str) -> str:
    """Archive/delete a calculator.
    
    Args:
        calculator_id: The UUID of the calculator to delete.
    """
    calc = store.get(calculator_id)
    if not calc:
        return f"Calculator with ID {calculator_id} not found."
    
    calc.status = CalculatorStatus.ARCHIVED
    store.save(calc)
    return f"Calculator {calculator_id} successfully archived."

def list_calculators() -> List[Dict[str, str]]:
    """List all active calculators for the current user/session."""
    calcs = store.list_all()
    active_calcs = [c for c in calcs if c.status != CalculatorStatus.ARCHIVED]
    
    return [
        {
            "id": c.id,
            "name": c.name,
            "description": c.description,
        }
        for c in active_calcs
    ]
