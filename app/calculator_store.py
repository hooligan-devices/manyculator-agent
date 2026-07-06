"""Firestore-backed storage for generated calculators.

This module provides the default production storage layer, persisting the
CalculatorDefinition models (including A2UI schemas and Python logic) to a
dedicated Google Cloud Firestore database named 'calculators'.
"""

import logging
from typing import List, Optional
from google.cloud import firestore

from .models.calculator import CalculatorDefinition

logger = logging.getLogger(__name__)

class CalculatorStore:
    """Manages persistent storage of calculators using Google Cloud Firestore."""
    
    def __init__(self):
        """Initializes the Firestore client.
        
        Attempts to connect to a specific named database ('calculators').
        Fails gracefully by logging the error if ADC credentials or the database
        are missing.
        """
        try:
            # Initialize Firestore client pointing to the 'calculators' database
            self.db = firestore.Client(database="calculators")
            self.collection = self.db.collection("calculators")
        except Exception as e:
            logger.error(f"Failed to initialize Firestore client: {e}")
            self.db = None
            self.collection = None

    def save(self, calc: CalculatorDefinition):
        """Persist a newly generated calculator to Firestore.
        
        Serializes the Pydantic model directly to a Firestore document.
        
        Args:
            calc: The fully generated CalculatorDefinition model.
        """
        if not self.collection:
            logger.error("Cannot save: Firestore client not initialized.")
            return
            
        try:
            self.collection.document(calc.id).set(calc.model_dump(mode="json"))
            logger.info(f"Successfully saved calculator {calc.id} to Firestore.")
        except Exception as e:
            logger.error(f"Failed to save calculator {calc.id} to Firestore: {e}")

    def get(self, calc_id: str) -> Optional[CalculatorDefinition]:
        """Retrieve a specific calculator from Firestore by its UUID.
        
        Args:
            calc_id: The UUID string of the calculator.
            
        Returns:
            The parsed CalculatorDefinition model, or None if not found or on error.
        """
        if not self.collection:
            logger.error("Cannot get: Firestore client not initialized.")
            return None
            
        try:
            doc = self.collection.document(calc_id).get()
            if doc.exists:
                return CalculatorDefinition.model_validate(doc.to_dict())
            return None
        except Exception as e:
            logger.error(f"Failed to get calculator {calc_id} from Firestore: {e}")
            return None
        
    def list_all(self) -> List[CalculatorDefinition]:
        """Retrieve all calculators stored in the database.
        
        Returns:
            A list of all valid CalculatorDefinition models. Invalid documents
            are skipped and logged as warnings.
        """
        if not self.collection:
            logger.error("Cannot list: Firestore client not initialized.")
            return []
            
        calculators = []
        try:
            docs = self.collection.stream()
            for doc in docs:
                try:
                    calculators.append(CalculatorDefinition.model_validate(doc.to_dict()))
                except Exception as e:
                    logger.warning(f"Skipping invalid calculator document {doc.id}: {e}")
            return calculators
        except Exception as e:
            logger.error(f"Failed to list calculators from Firestore: {e}")
            return []

store = CalculatorStore()

