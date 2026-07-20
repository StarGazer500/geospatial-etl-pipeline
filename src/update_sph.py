"""
update_sph.py
-------------
Updates the sph column in the local subcompartments table by computing it
from the espacement column.

Espacement format: 'row x col'  e.g. '10 x 2.5'
SPH formula: 10000 / row / col  e.g. 10000 / 10 / 2.5 = 400

Usage:
    python update_sph.py                        # updates all schemas
    python update_sph.py akwaaba_schema         # updates one schema
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

load_dotenv()

HOST     = os.getenv('SOURCE_HOST')
PORT     = os.getenv('SOURCE_PORT')
DB       = os.getenv('SOURCE_DATABASE_NAME')
USER     = os.getenv('SOURCE_USERNAME')
PASSWORD = os.getenv('SOURCE_PASSWORD')

SCHEMAS = ['akwaaba_schema', 'buffalo_schema_baseline','buffalo_schema_operational', 'colobus_schema']


def update_subcompartment_sph(engine, schema):
    sql = text(f"""
        UPDATE "{schema}".subcompartments
        SET sph = ROUND(
            10000.0
            / NULLIF(SPLIT_PART(REGEXP_REPLACE(TRIM(planting_type), '\\s*[xX]\\s*', ' x ', 'g'), ' x ', 1)::NUMERIC, 0)
            / NULLIF(SPLIT_PART(REGEXP_REPLACE(TRIM(planting_type), '\\s*[xX]\\s*', ' x ', 'g'), ' x ', 2)::NUMERIC, 0)
        )
        WHERE planting_type ~ '^\\s*\\d+\\.?\\d*\\s*[xX]\\s*\\d+\\.?\\d*\\s*$'
    """)
    with engine.connect() as conn:
        result = conn.execute(sql)
        conn.commit()
        print(f'{schema} subcompartments sph updated: {result.rowcount} rows')


def main():
    schemas = sys.argv[1:] if len(sys.argv) > 1 else SCHEMAS

    engine = create_engine(
        URL.create(
            drivername='postgresql+psycopg2',
            username=USER,
            password=PASSWORD,
            host=HOST,
            port=int(PORT),
            database=DB,
        ),
        pool_pre_ping=True
    )

    try:
        for schema in schemas:
            try:
                update_subcompartment_sph(engine, schema)
            except Exception as e:
                print(f'{schema} sph update failed: {e}')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
