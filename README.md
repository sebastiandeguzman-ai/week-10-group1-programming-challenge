# Week 10 Programming Challenge by Group 1

A Python pipeline that recovers, validates, and reconciles country records from four file formats, performs data analysis using Pandas and NumPy, and generates validated datasets and summary tables.

## Dataset Information

- **Dataset:** Historical Gapminder Dataset
- **Source:** DSA4153 Week 10 Group Task Inputs (Canvas)
- **Input Files:** `country_records.csv`, `country_records.xlsx`, `country_records.json`, `country_records.parquet`
- **Historical Coverage:** 1952–2007
- **Original Observations:** 1,704
- **Expected Raw Rows per File:** 1,712
- **Invalid Records per File:** 6
- **Duplicate Copies per File:** 2
- **Expected Canonical Records:** 1,704

The dataset is provided through Canvas and is **not included** in this repository.

## Requirements

- Python 3.10 or newer
- Git
- Dependencies listed in `requirements.txt` (pandas, numpy, openpyxl, pyarrow)

## Setup & Running

### 1. Clone the repository

```bash
git clone https://github.com/sebastiandeguzman-ai/week-10-group1-programming-challenge.git
cd week-10-group1-programming-challenge
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Download the dataset

1. Download `DSA4153_Week10_Group_Task_Inputs.zip` from Canvas.
2. Extract the files into the `data/` folder.
3. Make sure the four input files and `manifest.json` are in the correct location.

### 5. Run the pipeline

Run this from the **repository root**:

```bash
python main.py --config config.json
```

## What the Pipeline Does

| Phase | What happens |
|-------|--------------|
| 1. Read | Loads the four input formats and extracts their records. |
| 2. Standardize | Maps the columns into the required canonical format. |
| 3. Validate | Checks missing values, invalid data types, and values outside the allowed rules. |
| 4. Clean | Quarantines invalid records and removes exact duplicates. |
| 5. Reconcile | Compares the four datasets and checks for conflicting records. |
| 6. Analyze | Performs country, population, and life expectancy analysis using Pandas and NumPy. |
| 7. Export | Saves the canonical dataset and analytical results. |
| 8. Verify | Reloads exported files and checks their contents against the validated dataset. |

## Outputs

All results are written to the configured output folder:

| File | Description |
|------|-------------|
| `canonical.csv` | Cleaned dataset in CSV format |
| `canonical.xlsx` | Cleaned dataset in Excel format |
| `canonical.json` | Cleaned dataset in JSON format |
| `canonical.parquet` | Cleaned dataset in Parquet format |
| `asia_selected_year.csv` | Asian country records for the selected reporting year, including population and life expectancy rankings |
| `country_history.csv` | Historical records for the Philippines |
| `population_index.csv` | Population index of the Philippines, Indonesia, and Thailand |
| `quarantine.csv` | Invalid records and their rejection reasons |
| `duplicate_log.csv` | Exact duplicate records removed |
| `validation.csv` | Results of the validation checks |
| `audit_log.csv` | Step-by-step record of pipeline operations |
| `test_results.txt` | Results of the automated tests |

## Project Structure

```text
week-10-group1-programming-challenge/

├── data/
│   ├── country_records.csv
│   ├── country_records.xlsx
│   ├── country_records.json
│   ├── country_records.parquet
│   └── manifest.json
│
├── src/
│   ├── readers.py
│   ├── validator.py
│   ├── analytics.py
│   └── exporter.py
│
├── tests/
├── staging/
├── output/
├── main.py
├── config.json
├── requirements.txt
├── report.ipynb
├── contributions.csv
├── reviews.md
└── README.md
```

## Configuration

Paths and processing settings are defined in `config.json`:

- `DATA_PATH`: location of the input files.
- `OUTPUT_DIR`: location where results are saved.
- `REPORTING_YEAR`: year used for the selected-year analysis (default: `2007`).
- Column mappings and format settings: used to read and standardize the input files.

## Optional: Run Individual Modules

The project is divided into reusable modules:

- `readers.py`: reads and extracts records from the four formats.
- `validator.py`: validates records and handles duplicates and conflicts.
- `analytics.py`: performs the required Pandas and NumPy analysis.
- `exporter.py`: exports the cleaned dataset and analytical results.

## Troubleshooting

- **Missing input files**: Make sure the files are extracted into the `data/` folder.
- **Missing dependencies**: Activate your virtual environment and run `pip install -r requirements.txt`.
- **Invalid records**: Check `quarantine.csv` for the rejection reasons.
- **Duplicate records**: Check `duplicate_log.csv` for removed copies.
- **Conflicting records**: Check the reported country and year keys. Conflicting records stop the pipeline.
- **Validation failure**: Check `validation.csv` for the expected and actual values.
- **Configuration errors**: Verify the file paths and settings in `config.json`.
- **Module errors**: Run the program from the repository root.

