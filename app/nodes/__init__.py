"""Workflow nodes package for the Manyculator calculator-generation agent.

This package re-exports every node in the ADK Workflow graph so that
``agent.py`` can import them from a single location::

    from app.nodes import blueprint_generator, script_validator, ...

The workflow contains two categories of nodes:

* **Agent Nodes** (4) – LLM-powered nodes that use a model to generate or
  evaluate content (blueprints, scripts, UI schemas, and quality judgments).
* **Function Nodes** (3) – Deterministic, code-only nodes that perform
  validation or infrastructure checks without calling an LLM.

The two remaining node types in the full graph (router nodes
``script_validator_router`` and ``script_judge_router``) are defined inline
in ``agent.py`` because they are thin routing lambdas, not standalone modules.
"""

# ---------------------------------------------------------------------------
# Agent Nodes – each wraps an LLM call with a structured prompt
# ---------------------------------------------------------------------------
from .blueprint_generator import blueprint_generator  # Analyzes user intent → structured calculator blueprint
from .script_generator import script_generator        # Blueprint → sandboxed Python calculation script
from .ui_schema_generator import ui_schema_generator  # Blueprint → A2UI declarative UI schema (JSON)
from .script_judge import script_judge                # LLM judge verifying script ↔ UI schema consistency

# ---------------------------------------------------------------------------
# Function Nodes – pure-Python, no LLM; deterministic checks & side-effects
# ---------------------------------------------------------------------------
from .sandbox_check import sandbox_check              # Verifies GKE gVisor sandbox health on startup
from .script_validator import script_validator        # Syntax & structure validation of generated scripts
from .ui_schema_validator import ui_schema_validator  # Validates A2UI JSON against the SDK schema

__all__ = [
    # Agent Nodes
    "blueprint_generator",
    "script_generator",
    "ui_schema_generator",
    "script_judge",
    # Function Nodes
    "sandbox_check",
    "script_validator",
    "ui_schema_validator",
]
