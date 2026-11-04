import pandas as pd
import json

# JSON
with open("country_records.json", "r") as f:
    data = json.load(f)

dfjson = pd.json_normalize(
    data,
    record_path=["records"],
    meta=[
        ["metadata", "purpose"],
        ["metadata", "source_rows"],
        ["metadata", "raw_records"]
    ]
)
