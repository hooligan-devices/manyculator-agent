"""Integration tests for the POST /evaluate/{calculator_id} endpoint.

These tests verify the execution layer in isolation — no LLM calls are made.
A known-good CalculatorDefinition with a hardcoded script is injected directly
into the in-memory store, then the /evaluate endpoint is called via TestClient.
"""
import pytest
import datetime
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def mock_store(monkeypatch):
    """Mock the calculator store to prevent real Firestore calls during tests."""
    class FakeStore:
        def __init__(self):
            self._calcs = {}
        def save(self, calc):
            self._calcs[calc.id] = calc
        def get(self, calc_id):
            return self._calcs.get(calc_id)
        def list_all(self):
            return list(self._calcs.values())
            
    fake_store = FakeStore()
    monkeypatch.setattr("app.calculator_store.store", fake_store)
    # The endpoint uses crud_tools.get_calculator, which relies on crud_tools.store
    monkeypatch.setattr("app.tools.crud_tools.store", fake_store)
    
    # We must yield the fake store so the saved_calculator fixture can use it
    yield fake_store
@pytest.fixture
def client():
    """Create a FastAPI TestClient for the calc_agent app."""
    from app.fast_api_app import app
    return TestClient(app)


@pytest.fixture
def saved_calculator(mock_store):
    """Save a known-good calculator to the in-memory store and return it."""
    from app.models.calculator import CalculatorDefinition, CalculatorStatus

    script = '''
def calculate(inputs: dict) -> dict:
    bill = float(inputs.get("bill_amount", 0))
    tip_pct = float(inputs.get("tip_percentage", 15))
    tip = bill * (tip_pct / 100)
    total = bill + tip
    return {"tip_amount": round(tip, 2), "total": round(total, 2)}
'''

    calc = CalculatorDefinition(
        id="test-calc-001",
        name="Tip Calculator",
        description="Calculates tip and total for a restaurant bill.",
        created_at=datetime.datetime.now(),
        updated_at=datetime.datetime.now(),
        status=CalculatorStatus.ACTIVE,
        parameters=[],
        script=script,
        a2ui_schema={
            "title": "Tip Calculator",
            "inputs": [
                {"id": "bill_amount", "component_type": "number_input", "label": "Bill Amount"},
                {"id": "tip_percentage", "component_type": "slider", "label": "Tip %"},
            ],
            "outputs": [
                {"id": "tip_amount", "component_type": "result_display", "label": "Tip"},
                {"id": "total", "component_type": "result_display", "label": "Total"},
            ],
        },
        original_prompt="Create a tip calculator",
    )
    mock_store.save(calc)
    return calc


class TestEvaluateEndpoint:
    """Tests for POST /evaluate/{calculator_id}."""

    def test_successful_evaluation(self, client, saved_calculator):
        """Happy path: compute tip and total from valid inputs."""
        response = client.post(
            f"/evaluate/{saved_calculator.id}",
            json={"inputs": {"bill_amount": 100, "tip_percentage": 20}},
        )
        assert response.status_code == 200
        data = response.json()
        assert "outputs" in data
        assert data["outputs"]["tip_amount"] == 20.0
        assert data["outputs"]["total"] == 120.0

    def test_different_inputs(self, client, saved_calculator):
        """Verify outputs change reactively when inputs change."""
        # First call
        r1 = client.post(
            f"/evaluate/{saved_calculator.id}",
            json={"inputs": {"bill_amount": 50, "tip_percentage": 10}},
        )
        assert r1.status_code == 200
        assert r1.json()["outputs"]["tip_amount"] == 5.0
        assert r1.json()["outputs"]["total"] == 55.0

        # Second call with different inputs
        r2 = client.post(
            f"/evaluate/{saved_calculator.id}",
            json={"inputs": {"bill_amount": 200, "tip_percentage": 25}},
        )
        assert r2.status_code == 200
        assert r2.json()["outputs"]["tip_amount"] == 50.0
        assert r2.json()["outputs"]["total"] == 250.0

    def test_default_values(self, client, saved_calculator):
        """Verify defaults are applied when optional inputs are omitted."""
        response = client.post(
            f"/evaluate/{saved_calculator.id}",
            json={"inputs": {"bill_amount": 80}},
        )
        assert response.status_code == 200
        # Default tip_percentage is 15
        assert response.json()["outputs"]["tip_amount"] == 12.0
        assert response.json()["outputs"]["total"] == 92.0

    def test_zero_inputs(self, client, saved_calculator):
        """Verify zero inputs produce zero outputs."""
        response = client.post(
            f"/evaluate/{saved_calculator.id}",
            json={"inputs": {"bill_amount": 0, "tip_percentage": 20}},
        )
        assert response.status_code == 200
        assert response.json()["outputs"]["tip_amount"] == 0.0
        assert response.json()["outputs"]["total"] == 0.0

    def test_calculator_not_found(self, client):
        """404 when calculator_id does not exist."""
        response = client.post(
            "/evaluate/nonexistent-id",
            json={"inputs": {"bill_amount": 100}},
        )
        assert response.status_code == 404

    def test_get_schema_success(self, client, saved_calculator):
        """Happy path: retrieve the correct A2UI schema for a calculator."""
        response = client.get(f"/schema/{saved_calculator.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Tip Calculator"
        assert len(data["inputs"]) == 2

    def test_get_schema_not_found(self, client):
        """404 when requesting schema for a nonexistent calculator_id."""
        response = client.get("/schema/nonexistent-id")
        assert response.status_code == 404

    def test_calculator_without_script(self, client):
        """500 when calculator exists but has no script."""
        from app.calculator_store import store
        from app.models.calculator import CalculatorDefinition, CalculatorStatus

        calc = CalculatorDefinition(
            id="test-no-script",
            name="Empty Calculator",
            description="No script",
            created_at=datetime.datetime.now(),
            updated_at=datetime.datetime.now(),
            status=CalculatorStatus.ACTIVE,
            parameters=[],
            script="",
            original_prompt="test",
        )
        store.save(calc)

        response = client.post(
            "/evaluate/test-no-script",
            json={"inputs": {"x": 1}},
        )
        assert response.status_code == 500

    def test_empty_inputs(self, client, saved_calculator):
        """Endpoint works with empty inputs dict (script uses defaults)."""
        response = client.post(
            f"/evaluate/{saved_calculator.id}",
            json={"inputs": {}},
        )
        assert response.status_code == 200
        # bill_amount defaults to 0, tip_percentage to 15
        assert response.json()["outputs"]["tip_amount"] == 0.0
        assert response.json()["outputs"]["total"] == 0.0


class TestEvaluateWithComplexScript:
    """Tests with a more complex calculator script (BMI)."""

    @pytest.fixture
    def bmi_calculator(self):
        from app.calculator_store import store
        from app.models.calculator import CalculatorDefinition, CalculatorStatus

        script = '''
def calculate(inputs: dict) -> dict:
    height_cm = float(inputs.get("height_cm", 170))
    weight_kg = float(inputs.get("weight_kg", 70))
    height_m = height_cm / 100
    if height_m <= 0:
        return {"bmi": 0.0, "category": "invalid"}
    bmi = weight_kg / (height_m ** 2)
    if bmi < 18.5:
        category = "underweight"
    elif bmi < 25:
        category = "normal"
    elif bmi < 30:
        category = "overweight"
    else:
        category = "obese"
    return {"bmi": round(bmi, 1), "category": category}
'''

        calc = CalculatorDefinition(
            id="test-bmi-001",
            name="BMI Calculator",
            description="Calculates BMI from height and weight.",
            created_at=datetime.datetime.now(),
            updated_at=datetime.datetime.now(),
            status=CalculatorStatus.ACTIVE,
            parameters=[],
            script=script,
            original_prompt="Make a BMI calculator",
        )
        store.save(calc)
        return calc

    def test_bmi_normal(self, client, bmi_calculator):
        response = client.post(
            f"/evaluate/{bmi_calculator.id}",
            json={"inputs": {"height_cm": 175, "weight_kg": 70}},
        )
        assert response.status_code == 200
        outputs = response.json()["outputs"]
        assert outputs["bmi"] == 22.9
        assert outputs["category"] == "normal"

    def test_bmi_overweight(self, client, bmi_calculator):
        response = client.post(
            f"/evaluate/{bmi_calculator.id}",
            json={"inputs": {"height_cm": 170, "weight_kg": 85}},
        )
        assert response.status_code == 200
        outputs = response.json()["outputs"]
        assert outputs["bmi"] == 29.4
        assert outputs["category"] == "overweight"

    def test_bmi_edge_zero_height(self, client, bmi_calculator):
        response = client.post(
            f"/evaluate/{bmi_calculator.id}",
            json={"inputs": {"height_cm": 0, "weight_kg": 70}},
        )
        assert response.status_code == 200
        outputs = response.json()["outputs"]
        assert outputs["bmi"] == 0.0
        assert outputs["category"] == "invalid"
