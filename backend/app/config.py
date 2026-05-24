"""Application configuration via environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from `.env` and environment."""

    model_config = SettingsConfigDict(
        env_file=".env",  # Carrega variáveis do arquivo .env
        env_file_encoding="utf-8",
        extra="ignore",  # Ignora chaves extras no .env
    )

    database_host: str = Field(default="127.0.0.1", alias="DATABASE_HOST")  # Host MySQL
    database_port: int = Field(default=3306, alias="DATABASE_PORT")  # Porta MySQL
    database_user: str = Field(default="root", alias="DATABASE_USER")  # Usuário MySQL
    database_password: str = Field(default="", alias="DATABASE_PASSWORD")  # Senha MySQL
    database_name: str = Field(default="pbx", alias="DATABASE_NAME")  # Nome do schema/banco

    api_key: str = Field(..., alias="API_KEY")  # Deve bater com o header X-API-Key

    external_status_url: str | None = Field(default=None, alias="EXTERNAL_STATUS_URL")  # URL opcional (probe no startup)
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")

settings = Settings()  # Instância única usada em todo o app
