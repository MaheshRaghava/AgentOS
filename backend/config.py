from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Gemini
    gemini_api_key: str
    gemini_model: str = "gemini-3.5-flash"

    # Model fallback chain — all verified from ListModels output
    gemini_model_chain: list[str] = [
        "gemini-3.5-flash",        # Primary — cutting edge, high quota
        "gemini-3.1-flash-lite",   # Fast rescue layer
        "gemini-2.5-flash",        # Separate quota pool — 3rd fallback
        "gemini-2.5-flash-lite",   # Lightweight fallback
        "gemini-2.5-pro",          # Elite logic — last resort (low quota)
    ]

    # Redis
    redis_url: str = "redis://localhost:6379"

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "agentos"
    mongodb_db_name: str = "agentos"

    # Tavily (web search)
    tavily_api_key: str = ""

    # App
    frontend_url: str = "http://localhost:5173"
    debug: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
