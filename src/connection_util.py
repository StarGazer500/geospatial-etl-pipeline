
from sqlalchemy import text, create_engine





class DatabaseConnection:

    val_conn = None
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
    def connect_to_source_postgis_database(cls,host,database_name,port,username,password):
        try:
            
            conn = DatabaseConnection._create_engine(
                host, database_name, port,
                username, password, "SOURCE"
            )
            
            print("Source database connection successful!")
            return conn
            
        except Exception as e:
            print(f'Error connecting to Source database: {e}')
            return None
        
    @classmethod
    def connect_to_validation_postgis_database(cls,host,database_name,port,username,password):
        try:
            if not cls.val_conn:
                conn = DatabaseConnection._create_engine(
                    host, database_name, port,
                    username, password, "VALIDATION"
                )
                cls.val_conn = conn
                print("Validation database connection successful!")
                return cls.val_conn
            else:
                print("Validation database connection successful!")
                return cls.val_conn
        except Exception as e:
            print(f'Error connecting to Validation database: {e}')
            return None



    @classmethod
    def connect_to_target_postgis_database(cls,host,database_name,port,username,password):
        try:
            if not cls.target_conn:
                conn = DatabaseConnection._create_engine(
                    host, database_name, port,
                    username, password, "TARGET"
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
