"""Local JSON-backed storage for generated calculators.

This module provides a local testing alternative to Firestore. It persists
CalculatorDefinition models to a 'calculators_db.json' file at the project root,
allowing rapid offline development without requiring Google Cloud resources.
"""

import json
import os
from typing import Dict, List, Optional
from .models.calculator import CalculatorDefinition

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "calculators_db.json")

class CalculatorStore:
    """Manages persistent storage of calculators using a local JSON file."""
    
    def __init__(self):
        """Initializes the local store and loads any existing calculators from disk."""
        self._calculators: Dict[str, CalculatorDefinition] = {}
        self._load()

    def _load(self):
        """Load calculators from the JSON file into memory.
        
        Silently skips the load if the file doesn't exist yet (e.g., on first run).
        Warns via logging if the JSON is corrupted or parsing fails.
        """
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
        """Serialize the in-memory cache and write it to the JSON file.
        
        Warns via logging if file write permissions fail.
        """
        try:
            with open(DB_PATH, "w") as f:
                data = {k: v.model_dump(mode="json") for k, v in self._calculators.items()}
                json.dump(data, f, indent=2)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to save calculators db: {e}")

    def save(self, calc: CalculatorDefinition):
        """Cache the calculator in memory and sync the entire store to disk.
        
        Args:
            calc: The fully generated CalculatorDefinition model.
        """
        self._calculators[calc.id] = calc
        self._save_to_disk()

    def get(self, calc_id: str) -> Optional[CalculatorDefinition]:
        """Retrieve a specific calculator from the in-memory cache.
        
        Args:
            calc_id: The UUID string of the calculator.
            
        Returns:
            The CalculatorDefinition model, or None if not found.
        """
        return self._calculators.get(calc_id)
        
    def list_all(self) -> List[CalculatorDefinition]:
        """Retrieve all calculators currently loaded in memory.
        
        Returns:
            A list of all valid CalculatorDefinition models.
        """
        return list(self._calculators.values())

store = CalculatorStore()

