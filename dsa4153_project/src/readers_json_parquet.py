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
# PARQUET 
dfparquet = pd.read_parquet("country_records.parquet")

dfparquet = dfparquet.rename(columns={
    'COUNTRY': "country",
    'CONTINENT': 'continent',
    'YEAR': 'year',
    'LIFE_EXP': 'lifeExp',
    'POPULATION': 'pop',
    'GDP_PER_CAPITA': 'gdpPercap'
})

print(dfparquet.dtypes)
print(dfparquet.head())

# CHECKING
REQUIRED_COLUMNS = [
    'country',
    'continent',
    'year',
    'lifeExp',
    'pop',
    'gdpPercap'
]

def check_missing_columns(df):
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]

    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    return True

def check_record_order(original_df, normalized_df):
    return original_df.index.equals(normalized_df.index)

check_missing_columns(dfjson)
check_missing_columns(dfparquet)
