import os
from sqlalchemy import text, create_engine


source_host = os.getenv("SOURCE_HOST")
source_database_name = os.getenv("SOURCE_DATABASE_NAME")
source_port = os.getenv("SOURCE_PORT")
source_username = os.getenv("SOURCE_USERNAME")
source_password = os.getenv("SOURCE_PASSWORD")


target_host = os.getenv("TARGET_HOST")
target_database_name = os.getenv("TARGET_DATABASE_NAME")
target_port = os.getenv("TARGET_PORT")
target_username = os.getenv("TARGET_USERNAME")
target_password = os.getenv("TARGET_PASSWORD")


class DatabaseConnection:

    source_conn = None
    target_conn = None

    @staticmethod
    def _create_engine(host, database_name, port, username, password, db_type="database"):
        if not all([host, database_name, port, username, password]):
            raise ValueError(f"Missing required {db_type} environment variables")

        connection_base = f'{username}:{password}@{host}:{port}/{database_name}'

        sync_engine = create_engine(
            f'postgresql://{connection_base}',
            pool_size=3,
            max_overflow=0,
            pool_timeout=60,
            connect_args={"options": "-c lock_timeout=30000"},
        )

        # Test connection
        with sync_engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        return {'sync': sync_engine}



    @classmethod
    def connect_to_source_postgis_database(cls):
        try:
            if not cls.source_conn:
                conn = DatabaseConnection._create_engine(
                    source_host, source_database_name, source_port,
                    source_username, source_password, "SOURCE"
                )
                cls.source_conn = conn
                print("Source database connection successful!")
                return cls.source_conn
            else:
                print("Source database connection successful!")
                return cls.source_conn
        except Exception as e:
            print(f'Error connecting to Source database: {e}')
            return None



    @classmethod
    def connect_to_target_postgis_database(cls):
        try:
            if not cls.target_conn:
                conn = DatabaseConnection._create_engine(
                    target_host, target_database_name, target_port,
                    target_username, target_password, "TARGET"
                )
                cls.target_conn = conn
                print("Target database connection successful!")
                return cls.target_conn
            else:
                print("Target database connection successful!")
                return cls.target_conn
        except Exception as e:
            print(f'Error connecting to Target database: {e}')
            return None
