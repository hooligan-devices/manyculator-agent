"""Standalone smoke test for sandbox_executor.execute_calculation.

Validates that the local DummyExecutor can correctly run generated
calculator scripts and parse their JSON output. No FastAPI or LLM involved.

Usage:
    uv run python tests/scripts/test_sandbox_execution.py
"""
import json
import sys

# Force fresh executor on each run
from app.services.sandbox_executor import execute_calculation


def test_simple_addition():
    script = '''
def calculate(inputs: dict) -> dict:
    a = float(inputs.get("a", 0))
    b = float(inputs.get("b", 0))
    return {"sum": a + b}
'''
    result = execute_calculation(script, {"a": 3, "b": 7})
    assert result == {"sum": 10.0}, f"Expected {{'sum': 10.0}}, got {result}"
    print("  ✓ simple_addition")


def test_percentage_calculation():
    script = '''
def calculate(inputs: dict) -> dict:
    value = float(inputs.get("value", 0))
    percentage = float(inputs.get("percentage", 0))
    result = value * (percentage / 100)
    return {"result": round(result, 2)}
'''
    result = execute_calculation(script, {"value": 200, "percentage": 15})
    assert result == {"result": 30.0}, f"Expected {{'result': 30.0}}, got {result}"
    print("  ✓ percentage_calculation")


def test_multi_output():
    script = '''
def calculate(inputs: dict) -> dict:
    principal = float(inputs.get("principal", 0))
    rate = float(inputs.get("rate", 0)) / 100
    years = int(inputs.get("years", 1))
    amount = principal * ((1 + rate) ** years)
    interest = amount - principal
    return {"amount": round(amount, 2), "interest": round(interest, 2)}
'''
    result = execute_calculation(script, {"principal": 1000, "rate": 5, "years": 2})
    assert result["amount"] == 1102.5, f"Expected amount 1102.5, got {result['amount']}"
    assert result["interest"] == 102.5, f"Expected interest 102.5, got {result['interest']}"
    print("  ✓ multi_output")


def test_string_output():
    script = '''
def calculate(inputs: dict) -> dict:
    temp_c = float(inputs.get("celsius", 0))
    temp_f = temp_c * 9/5 + 32
    if temp_f > 100:
        status = "hot"
    elif temp_f > 60:
        status = "warm"
    else:
        status = "cold"
    return {"fahrenheit": round(temp_f, 1), "status": status}
'''
    result = execute_calculation(script, {"celsius": 37})
    assert result["fahrenheit"] == 98.6, f"Expected 98.6, got {result['fahrenheit']}"
    assert result["status"] == "warm", f"Expected 'warm', got {result['status']}"
    print("  ✓ string_output")


def test_empty_inputs():
    script = '''
def calculate(inputs: dict) -> dict:
    x = float(inputs.get("x", 42))
    return {"result": x}
'''
    result = execute_calculation(script, {})
    assert result == {"result": 42.0}, f"Expected {{'result': 42.0}}, got {result}"
    print("  ✓ empty_inputs")


def test_script_error_handling():
    script = '''
def calculate(inputs: dict) -> dict:
    x = float(inputs["missing_key"])
    return {"result": x}
'''
    result = execute_calculation(script, {})
    assert "error" in result, f"Expected error in result, got {result}"
    print("  ✓ script_error_handling")


def test_null_and_bool_inputs():
    script = '''
def calculate(inputs: dict) -> dict:
    bmi = inputs.get("bmi")
    is_metric = inputs.get("is_metric")
    return {"bmi_is_none": bmi is None, "is_metric": is_metric}
'''
    result = execute_calculation(script, {"bmi": None, "is_metric": True})
    assert result == {"bmi_is_none": True, "is_metric": True}, f"Expected match, got {result}"
    print("  ✓ null_and_bool_inputs")



if __name__ == "__main__":
    tests = [
        test_simple_addition,
        test_percentage_calculation,
        test_multi_output,
        test_string_output,
        test_empty_inputs,
        test_script_error_handling,
        test_null_and_bool_inputs,
    ]

    print("Running sandbox execution smoke tests...")
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {test.__name__}: UNEXPECTED ERROR: {e}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    sys.exit(1 if failed > 0 else 0)
