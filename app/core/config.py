from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la API. Todo override-able por variable de entorno
    (prefijo CUADRA_), en línea con el resto del repo (ver
    cuadra-data/config/connections.yml) -- nada de conexión hardcodeado.
    """

    model_config = SettingsConfigDict(env_prefix="CUADRA_", env_file=".env", extra="ignore")

    app_name: str = "Cuadra API"
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
    # app/repositories/sqlite/connection.py.
    sqlite_path: str = "app/data/cuadra.sqlite"


settings = Settings()
