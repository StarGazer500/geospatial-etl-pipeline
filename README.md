# ETL Pipeline

A geospatial ETL (Extract, Transform, Load) pipeline for migrating PostGIS data from Group Planning to Chameleon Geospatial databases. Runs asynchronously with async parallel processing, savepoint progress tracking, and automatic geometry validation.

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

## Setup

### Requirements

- Python 3.10+
- PostgreSQL with PostGIS extension
- Required packages: `asyncpg`, `psycopg2-binary`, `sqlalchemy`, `geopandas`, `pandas`, `diskcache`

### Environment Variables

Create a `.env` file or set the following environment variables:

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

## Usage

Open `notebook/etl_pipeline.ipynb` and run the cells:

1. **Connect** to source and target databases
2. **Validate** schemas (checks layer names and column names against requirements)
3. **Run ETL** for all three schemas in parallel

### Progress Tracking

The pipeline uses disk-based caching to track which layers have been loaded. On re-run, already-loaded layers are skipped. To force a fresh run:

```python
await SavePoints.clear_all_progress(is_clear_cache=True)
```

## Key Features

- **Async parallel processing** - All layers within a schema load concurrently via `asyncio.gather`
- **Geometry validation** - Invalid geometries are automatically fixed with `make_valid()` before saving
- **Schema auto-creation** - Target schemas are created if they don't exist
- **CRS conversion** - Geometries are reprojected to EPSG:4326 by default
- **Savepoints** - Failed runs can resume from where they left off
