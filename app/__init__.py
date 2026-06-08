"""
Autonomous Technical Document Intelligence & Workflow Automation Pipeline.

A self-built, production-style portfolio demo by Pulse Method.

The package simulates an end-to-end pipeline that ingests messy technical /
project documents, extracts structured data (simulated LLM step), validates the
result against a deterministic rule set and a reference catalog, and exposes the
output through a typed FastAPI service with job-status tracking.

NOTE: This is a demonstration system. The "LLM extraction" step is a deterministic
local simulation so the demo runs fully offline with no external credentials.
"""

__version__ = "1.0.0"
__author__ = "Pulse Method"
