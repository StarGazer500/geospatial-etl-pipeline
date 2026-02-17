# ETL Pipeline

A geospatial ETL (Extract, Transform, Load) pipeline for transforming PostGIS data from Raw  to Transforned and Cleaned data. Runs asynchronously with async parallel processing, savepoint progress tracking, and automatic geometry validation.

## Project Structure

```
etl_pipeline/
├── notebook/
│   └── etl_pipeline.ipynb      # Main entry point (Jupyter notebook)
├── src/
│   ├── connection_util.py      # Database connection management
│   ├── data_management_util.py # Spatial/non-spatial query execution and data saving
│   ├── etl_pipeline.py         # Pipeline orchestrator per schema
│   ├── etl_util.py             # ETL logic for each data layer
│   ├── savepoints_util.py      # Progress tracking with disk cache
│   └── validation_util.py      # Schema/column validation and geometry fixing
```

## Schemas and Layers

The pipeline processes three schemas, each with a different subset of layers:

| Layer                | akwaaba | buffalo | colobus |
|----------------------|---------|---------|---------|
| leased_areas         | x       | x       | x       |
| compartments         | x       | x       | x       |
| subcompartments      | x       | x       |         |
| unplantable_areas    | x       | x       | x       |
| field_mapped_farms   | x       |         | x       |
| intercropped_farms   | x       |         |         |
| rb_roads             | x       | x       | x       |
| assigned_psps        | x       | x       | x       |
| completed_psps       | x       | x       | x       |

## Prerequisites

- Python 3.10+
- PostgreSQL with PostGIS extension
- VS Code (recommended)

## Setup

### 1. Clone the Repository

```bash
git clone <repository-url>
cd etl_pipeline
```

### 2. Create a Virtual Environment

```bash
python -m venv etl_env
```

Activate the virtual environment:

- **Windows (Command Prompt):**
  ```cmd
  etl_env\Scripts\activate
  ```
- **Windows (PowerShell):**
  ```powershell
  etl_env\Scripts\Activate.ps1
  ```
- **Linux/macOS:**
  ```bash
  source etl_env/bin/activate
  ```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root with your database credentials:

```
# Source database (read from)
SOURCE_HOST=
SOURCE_DATABASE_NAME=
SOURCE_PORT=
SOURCE_USERNAME=
SOURCE_PASSWORD=

# Target database (write to)
TARGET_HOST=
TARGET_DATABASE_NAME=
TARGET_PORT=
TARGET_USERNAME=
TARGET_PASSWORD=
```

## Running in VS Code

### Install Required Extensions

Open VS Code and install the following extensions (from the Extensions tab `Ctrl+Shift+X`):

1. **Python** (`ms-python.python`) — Python language support
2. **Jupyter** (`ms-toolsai.jupyter`) — Jupyter notebook support

### Select the Python Interpreter

1. Open the Command Palette with `Ctrl+Shift+P`
2. Type **"Python: Select Interpreter"** and select it
3. Choose the `etl_env` virtual environment from the list (it will show as `./etl_env/Scripts/python.exe` on Windows)

### Run the Notebook

1. Open `notebook/etl_pipeline.ipynb` in VS Code
2. VS Code will render it as an interactive notebook
3. Make sure the kernel (top right of the notebook) is set to `etl_env`
4. Set `CLEAR_CACHE = True` in the second cell if you want a fresh run, or leave it as `False` to resume from the last savepoint
5. Click **"Run All"** at the top of the notebook, or run cells individually by clicking the play button next to each cell

### Progress Tracking

The pipeline uses disk-based caching (`cache_dir/`) to track which layers have been loaded. On re-run, already-loaded layers are skipped automatically. To force a fresh run, set `CLEAR_CACHE = True` in the notebook or call:

```python
await SavePoints.clear_all_progress(is_clear_cache=True)
```

## Key Features

- **Async parallel processing** - All layers within a schema load concurrently via `asyncio.gather`
- **Geometry validation** - Invalid geometries are automatically fixed with `make_valid()` before saving
- **Schema auto-creation** - Target schemas are created if they don't exist
- **CRS conversion** - Geometries are reprojected to EPSG:4326 by default
- **Savepoints** - Failed runs can resume from where they left off
