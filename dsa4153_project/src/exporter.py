"""Export, round-trip reload verification, staging, and audit logging module (Member 5)."""

from pathlib import Path
import json
import numpy as np
import pandas as pd


# Canonical schema contract mapping column names to target pandas dtypes
SCHEMA = {
    "country": "string",
    "continent": "string",
    "year": "int64",
    "lifeExp": "float64",
    "pop": "int64",
    "gdpPercap": "float64"
}

# Standard canonical column ordering required across all output formats
CANONICAL_COLUMNS = ["country", "continent", "year", "lifeExp", "pop", "gdpPercap"]