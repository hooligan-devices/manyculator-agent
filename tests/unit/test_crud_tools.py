import pytest
from datetime import datetime
from unittest.mock import patch

from app.models.calculator import CalculatorDefinition, CalculatorStatus

@pytest.fixture
def mock_store():
    # We mock the entire CalculatorStore singleton
    with patch("app.tools.crud_tools.store") as mock_store:
        yield mock_store

def test_get_calculator_strips_script(mock_store):
    from app.tools.crud_tools import get_calculator
    
    # Setup the mock to return a known CalculatorDefinition with a secret script
    calc = CalculatorDefinition(
        id="secret-123",
        name="Secret Calc",
        description="",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        status=CalculatorStatus.ACTIVE,
        parameters=[],
        script="def calculate(inputs): return {'secret_key': 42}",
        original_prompt="test",
        a2ui_schema={"components": []}
    )
    mock_store.get.return_value = calc
    
    # Call the tool function
    result = get_calculator("secret-123")
    
    # Assertions
    assert "error" not in result
    assert result["id"] == "secret-123"
    assert "a2ui_schema" in result
    
    # CRITICAL SECURITY CHECK: The frontend should never receive the raw Python script
    assert "script" not in result, "CRITICAL: get_calculator leaked the raw Python script!"

def test_delete_calculator(mock_store):
    from app.tools.crud_tools import delete_calculator
    
    calc = CalculatorDefinition(
        id="del-123",
        name="Delete Calc",
        description="",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        status=CalculatorStatus.ACTIVE,
        parameters=[],
        script="",
        original_prompt=""
    )
    mock_store.get.return_value = calc
    
    delete_calculator("del-123")
    
    # Verify the status was changed to ARCHIVED and saved
    assert calc.status == CalculatorStatus.ARCHIVED
    mock_store.save.assert_called_once_with(calc)

def test_list_calculators_filters_archived(mock_store):
    from app.tools.crud_tools import list_calculators
    
    c1 = CalculatorDefinition(id="c1", name="C1", description="", created_at=datetime.now(), updated_at=datetime.now(), status=CalculatorStatus.ACTIVE, parameters=[], script="", original_prompt="")
    c2 = CalculatorDefinition(id="c2", name="C2", description="", created_at=datetime.now(), updated_at=datetime.now(), status=CalculatorStatus.ARCHIVED, parameters=[], script="", original_prompt="")
    
    mock_store.list_all.return_value = [c1, c2]
    
    results = list_calculators()
    
    assert len(results) == 1
    assert results[0]["id"] == "c1"
    # Ensure it only returns summary data, not full schema/script
    assert "script" not in results[0]
    assert "a2ui_schema" not in results[0]
