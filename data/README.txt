Read manifest.json for layouts, aliases, types, units and controls.
The four country_records files each contain all 1704 original observations, six deliberately invalid appended records, and two extra copies of valid records, in different orders.
These defects were introduced for teaching and are not claims about the original dataset.
conflicting_key.csv uses canonical column names and contains 1705 valid-domain rows but one contradictory country-year key. It must cause failure.
missing_column.csv is missing pop and must cause failure. unsupported.txt exists and must be rejected as an unsupported format.
Both failure-test CSVs use UTF-8, comma separators, canonical column names and no comment lines. Configure their readers accordingly.
source_record is the one-based order of data records after parsing, excluding comments, headers and metadata.
