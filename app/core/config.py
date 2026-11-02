from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la API. Todo override-able por variable de entorno
    (prefijo CUADRA_), en línea con el resto del repo (ver
    cuadra-data/config/connections.yml) -- nada de conexión hardcodeado.
    """

    model_config = SettingsConfigDict(env_prefix="CUADRA_", env_file=".env", extra="ignore")

    app_name: str = "Cuadra API"
    # Clave con que se firman los JWT. El default sirve solo para desarrollo.
    # En AWS se usa jwt_secret_arn y este valor queda sin usar; arrancar en
    # producción con el default es un agujero (cualquiera que conozca el texto
    # firma un token válido para cualquier usuario), así que
    # app/core/security.py se niega a arrancar en ese caso.
    secret_key: str = "dev-secret-change-me"
    access_token_expire_minutes: int = 60 * 24 * 7  # 1 semana
    jwt_algorithm: str = "HS256"

    # Umbral below/in/above -- copiado del prototipo frontend (8%) y de
    # dbt_project.yml, no validado con datos reales. Parametrizado a
    # propósito (ver docs/market-intelligence.md §3 y §6).
    market_threshold_pct: float = 0.08

    # Tamaño de muestra mínimo para considerar una estadística de mercado
    # confiable. Copiado de dbt var `min_sample_size` -- mismo valor, mismo
    # motivo: no bloquear zonas con poco volumen mostrando una mediana
    # engañosa (ver docs/market-intelligence.md §6).
    market_min_sample_size: int = 5

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    upload_dir: str = "app/static/uploads"
    reports_dir: str = "app/static/reports"

    # Warehouse DuckDB de data_layer (dbt marts listings_unified/market_listings,
    # seed seed_barrios) -- ver app/repositories/warehouse/. Default relativo
    # asume el layout de hermanos ../cuadra-data junto a este repo (ver
    # cuadra-data/config/connections.yml para el mismo dato del lado data layer).
    data_layer_duckdb_path: str = "../cuadra-data/data/warehouse.duckdb"

    # SQLite operacional (usuarios, favoritos, consultas, informes) --
    # separado a propósito de data_layer_duckdb_path: ese warehouse es un
    # artefacto de dbt pensado para reconstruirse (dbt run/build), esto es
    # el registro transaccional que no puede perderse. Ver
    # app/repositories/sql/connection.py.
    #
    # Solo se usa cuando db_secret_arn está vacío (desarrollo y tests).
    sqlite_path: str = "app/data/cuadra.sqlite"

    # ARN del secreto de Secrets Manager con las credenciales de la RDS
    # (output AppDbSecretArn de infra/backend.yaml, el mismo secreto que
    # consume el job de Glue de cuadra-data). Cargado = los datos
    # operacionales van a Postgres en vez de al SQLite local; vacío = SQLite.
    # En AWS lo pone el user-data de la instancia como CUADRA_DB_SECRET_ARN.
    db_secret_arn: str = ""
    db_name: str = "alquileres"
    # TLS contra la base. En RDS va siempre prendido; se apaga solo para
    # correr contra un Postgres local sin certificados (ver
    # tests/test_sql_postgres.py).
    db_ssl: bool = True

    # ARN del secreto con la clave de firma de los JWT (output AppJwtSecretArn
    # de infra/backend.yaml). Cargado = se usa esa clave en vez de secret_key.
    # En AWS lo pone el user-data como CUADRA_JWT_SECRET_ARN.
    jwt_secret_arn: str = ""
    # Región para los clientes de boto3. Vacío = la que resuelva boto3 sola
    # (variable de entorno o metadata de la instancia).
    aws_region: str = ""

    # User pool de Cognito (outputs UserPoolId / UserPoolClientId de
    # infra/backend.yaml). Cargados = la API solo acepta ID tokens de Cognito
    # y las rutas de registro y login con contraseña quedan apagadas; el login
    # pasa a ser el hosted UI, con Google incluido. Vacíos = login propio con
    # bcrypt contra la tabla users, que es lo que corre en desarrollo y en los
    # tests. En AWS los pone el user-data como CUADRA_COGNITO_*.
    #
    # La región no se configura: sale del prefijo del pool id (ver
    # app/core/cognito.py).
    cognito_user_pool_id: str = ""
    cognito_client_id: str = ""


settings = Settings()
