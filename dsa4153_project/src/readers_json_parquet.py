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
dfjson = dfjson.rename(columns={
    'identity.country': 'country',
    'identity.continent': 'continent',
    'identity.year': 'year',
    'measures.lifeExp': 'lifeExp',
    'measures.pop': 'pop',
    'measures.gdpPercap': 'gdpPercap',
    'metadata.purpose': 'purpose',
    'metadata.source_rows': 'source_rows',
    'metadata.raw_records': 'raw_records',
})
