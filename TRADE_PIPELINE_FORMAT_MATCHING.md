# Trade Analysis Pipeline - Format Matching Issue

## Problem

The trade analysis pipeline (`trade_analysis_pipeline.py`) is **hardcoded to use CSV files** and does not support parquet format, despite the fact that `iwm_analysis.py` now saves results in matching formats (parquet in → parquet out).

### Current Behavior

**Line 197** - Hardcoded CSV loading:
```python
self.iwm_df = pd.read_csv('data/historical_iwm_0824_0825_with_indicators.csv')
```

**Output Files** - Always CSV:
- Line 273: `enriched_final.to_csv('data/trades_enriched.csv', index=False)`
- Line 879: `criteria_df.to_csv(output_filename, index=False)`
- Line 926: `criteria_results_df.to_csv('data/criteria_effectiveness.csv', index=False)`

### The Issue

When you run:
```bash
# Use parquet data in iwm_analysis
python iwm_analysis.py  # with parquet input from AlphaVantage

# This creates:
# - data/historical_iwm_*_with_indicators.parquet  ← parquet output
# - data/historical_iwm_*_signals.parquet           ← parquet output

# Then run trade analysis pipeline
python trade_analysis_pipeline.py

# ERROR: File not found!
# Looking for: data/historical_iwm_0824_0825_with_indicators.csv
# But only exists: data/historical_iwm_0824_0825_with_indicators.parquet
```

The pipeline **cannot find** the parquet files because it's only looking for CSV.

---

## Solution

The trade analysis pipeline needs to:

1. **Auto-detect** which format exists (CSV or parquet)
2. **Load** the appropriate format
3. **Save outputs** in the same format as the input

---

## Implementation

### 1. Add Format Detection (Line ~190)

**Add before line 197**:

```python
def step3_join_indicators(self):
    """Step 3: Join entry/exit with indicators from IWM data"""
    print("\n" + "="*60)
    print("STEP 3: JOIN WITH INDICATORS")
    print("="*60)

    # Auto-detect format (CSV or Parquet)
    from pathlib import Path
    import glob

    # Look for indicator files
    csv_files = glob.glob('data/historical_iwm_*_with_indicators.csv')
    parquet_files = glob.glob('data/historical_iwm_*_with_indicators.parquet')

    if parquet_files:
        indicator_file = parquet_files[0]  # Use most recent parquet file
        self.data_format = 'parquet'
        print(f"Detected parquet format: {indicator_file}")
        self.iwm_df = pd.read_parquet(indicator_file)
    elif csv_files:
        indicator_file = csv_files[0]  # Use most recent CSV file
        self.data_format = 'csv'
        print(f"Detected CSV format: {indicator_file}")
        self.iwm_df = pd.read_csv(indicator_file)
    else:
        raise FileNotFoundError(
            "No indicator files found! Run 'python iwm_analysis.py' first to generate "
            "data/historical_iwm_*_with_indicators.csv or .parquet"
        )

    # Rest of the method continues...
    self.iwm_df['Time'] = pd.to_datetime(self.iwm_df['Time'])
```

### 2. Update Enriched Trades Output (Line 273)

**Replace**:
```python
enriched_final.to_csv('data/trades_enriched.csv', index=False)
```

**With**:
```python
if self.data_format == 'parquet':
    enriched_final.to_parquet('data/trades_enriched.parquet', index=False)
    print("Saved trades_enriched.parquet with entry/exit indicators")
else:
    enriched_final.to_csv('data/trades_enriched.csv', index=False)
    print("Saved trades_enriched.csv with entry/exit indicators")
```

### 3. Update Criteria Analysis Output (Line 879)

**Replace**:
```python
criteria_df.to_csv(output_filename, index=False)
print(f"Created {len(criteria_df.columns)} columns in criteria analysis")
print(f"Saved to: {output_filename}")
```

**With**:
```python
if self.data_format == 'parquet':
    output_filename_parquet = output_filename.replace('.csv', '.parquet')
    criteria_df.to_parquet(output_filename_parquet, index=False)
    print(f"Created {len(criteria_df.columns)} columns in criteria analysis")
    print(f"Saved to: {output_filename_parquet}")
else:
    criteria_df.to_csv(output_filename, index=False)
    print(f"Created {len(criteria_df.columns)} columns in criteria analysis")
    print(f"Saved to: {output_filename}")
```

### 4. Update Criteria Effectiveness Output (Line 926)

**Replace**:
```python
criteria_results_df.to_csv('data/criteria_effectiveness.csv', index=False)
print(f"\nSaved detailed criteria effectiveness to: data/criteria_effectiveness.csv")
```

**With**:
```python
if self.data_format == 'parquet':
    criteria_results_df.to_parquet('data/criteria_effectiveness.parquet', index=False)
    print(f"\nSaved detailed criteria effectiveness to: data/criteria_effectiveness.parquet")
else:
    criteria_results_df.to_csv('data/criteria_effectiveness.csv', index=False)
    print(f"\nSaved detailed criteria effectiveness to: data/criteria_effectiveness.csv")
```

### 5. Update Cached DataFrame Loading (Line 37)

The `_get_cached_df()` method also needs format detection:

**Replace**:
```python
def _get_cached_df(self, key, file_path):
    """Get DataFrame from cache or read from file if not cached"""
    if self._cache[key] is None:
        if os.path.exists(file_path):
            self._cache[key] = pd.read_csv(file_path)
    return self._cache[key]
```

**With**:
```python
def _get_cached_df(self, key, file_path):
    """Get DataFrame from cache or read from file if not cached"""
    if self._cache[key] is None:
        # Try parquet first, then CSV
        parquet_path = file_path.replace('.csv', '.parquet')
        if os.path.exists(parquet_path):
            self._cache[key] = pd.read_parquet(parquet_path)
        elif os.path.exists(file_path):
            self._cache[key] = pd.read_csv(file_path)
    return self._cache[key]
```

### 6. Initialize Format Attribute (Line ~20)

Add to `__init__` method:

```python
def __init__(self):
    self.trades_df = None
    self.iwm_df = None
    self.pivoted_trades = None
    self.search_months = 1  # Default to 1 month
    self.data_format = 'csv'  # Default to CSV, detected in step3

    # Phase 3: DataFrame cache to avoid re-reading CSVs
    self._cache = {
        'similar_trades': None,
        'criteria_effectiveness': None,
        'trades_enriched': None
    }
```

---

## Testing

After implementation:

### Test 1: CSV Workflow
```bash
# Generate CSV output
python iwm_analysis.py -months 1

# Output: data/historical_iwm_*_with_indicators.csv

# Run pipeline
python trade_analysis_pipeline.py

# Should detect CSV format and output:
# - data/trades_enriched.csv
# - data/similar_trades_pipeline.csv
# - data/criteria_effectiveness.csv
```

### Test 2: Parquet Workflow
```bash
# Use parquet data (from AlphaVantage)
python iwm_analysis.py  # Using parquet input

# Output: data/historical_iwm_*_with_indicators.parquet

# Run pipeline
python trade_analysis_pipeline.py

# Should detect parquet format and output:
# - data/trades_enriched.parquet
# - data/similar_trades_pipeline.parquet
# - data/criteria_effectiveness.parquet
```

---

## Benefits

1. **Format Consistency**: Parquet in → Parquet out throughout entire pipeline
2. **File Size**: Parquet files are 5-10x smaller than CSV
3. **Performance**: Faster read/write operations with parquet
4. **Data Integrity**: Parquet preserves data types (no string conversions)
5. **Backward Compatible**: Still works with existing CSV workflows

---

## Files Modified

1. **`trade_analysis_pipeline.py`**:
   - Line ~20: Add `self.data_format` attribute
   - Line ~37: Update `_get_cached_df()` for format detection
   - Line ~190-197: Add format auto-detection in `step3_join_indicators()`
   - Line 273: Format-aware enriched trades output
   - Line 879: Format-aware criteria analysis output
   - Line 926: Format-aware criteria effectiveness output

---

## Summary

The trade analysis pipeline currently **only works with CSV files** and will fail if you use parquet output from `iwm_analysis.py`.

The fix adds:
- ✅ Auto-detection of CSV vs Parquet input
- ✅ Format-matching outputs (parquet in → parquet out)
- ✅ Backward compatibility with existing CSV workflows
- ✅ Better error messages when files not found

This ensures the entire pipeline maintains format consistency from data fetching → analysis → trade validation.
