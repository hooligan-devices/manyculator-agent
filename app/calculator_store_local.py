import json
import os
from typing import Dict, List, Optional
from .models.calculator import CalculatorDefinition

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "calculators_db.json")

class CalculatorStore:
    def __init__(self):
        self._calculators: Dict[str, CalculatorDefinition] = {}
        self._load()

    def _load(self):
        if os.path.exists(DB_PATH):
            try:
                with open(DB_PATH, "r") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        self._calculators[k] = CalculatorDefinition.model_validate(v)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to load calculators db: {e}")

    def _save_to_disk(self):
        try:
            with open(DB_PATH, "w") as f:
                data = {k: v.model_dump(mode="json") for k, v in self._calculators.items()}
                json.dump(data, f, indent=2)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to save calculators db: {e}")

    def save(self, calc: CalculatorDefinition):
        self._calculators[calc.id] = calc
        self._save_to_disk()

    def get(self, calc_id: str) -> Optional[CalculatorDefinition]:
        return self._calculators.get(calc_id)
        
    def list_all(self) -> List[CalculatorDefinition]:
        return list(self._calculators.values())

store = CalculatorStore()
