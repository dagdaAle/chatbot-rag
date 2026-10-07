"""Configurazione da variabili ambiente."""
from pydantic_settings import BaseSettings
from pathlib import Path
import os
import json

DATA_DIR = Path(os.getenv("DATA_DIR", str(Path(__file__).parent.parent / "data")))


class Settings(BaseSettings):
    """Impostazioni applicazione."""

    supabase_url: str = "https://supabase.intecha.dev"
    supabase_publishable_key: str = "sb_publishable_eOn6jCKOJYVPzRh39CQIFJ_0zYEU4iV"
    supabase_jwt_issuer: str = ""

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"
    
    # Provider LLM: "openai" o "ollama"
    llm_provider: str = "deepseek"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_chat_model: str = "deepseek-flash"
    embedding_provider: str = "ollama"
    openai_api_key: str = ""
    openai_base_url: str = ""  # Es: https://api.deepseek.com (vuoto = default OpenAI)
    openai_chat_model: str = "gpt-4o-mini"  # Default per chat
    openai_embedding_model: str = "text-embedding-3-small"  # Default per embedding
    openai_embedding_base_url: str = ""  # URL per embedding (vuoto = default OpenAI)
    openai_embedding_api_key: str = ""  # Chiave separata per embedding (vuoto = usa openai_api_key)
    
    # Configurazione Ollama
    # Ollama gira sul Mac Mini host (non in Docker)
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_chat_model: str = "llama3.2"  # Modello per chat
    ollama_embedding_model: str = "nomic-embed-text"  # Modello per embeddings

    @property
    def qdrant_url(self) -> str:
        """URL Qdrant."""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()


class RuntimeConfig:
    """Configurazione runtime modificabile e persistita in DATA_DIR.
    
    Chat e embedding hanno provider INDIPENDENTI:
    - Puoi usare Ollama per la chat e OpenAI per gli embedding (o viceversa).
    """

    def __init__(self) -> None:
        # Provider e modello per la CHAT
        self.chat_provider: str = settings.llm_provider
        self.chat_model: str = self._default_chat_model()
        
        # Provider e modello per gli EMBEDDING (indipendente dalla chat)
        self.embedding_provider: str = settings.embedding_provider
        self.embedding_model: str = (settings.ollama_embedding_model if self.embedding_provider == "ollama" else settings.openai_embedding_model)
        config_path = DATA_DIR / "runtime_config.json"
        if config_path.exists():
            data = json.loads(config_path.read_text())
            for key in ("chat_provider", "chat_model", "embedding_provider", "embedding_model"):
                if key in data:
                    setattr(self, key, data[key])

    def save(self) -> None:
        from app.core.storage import write_json
        write_json(DATA_DIR / "runtime_config.json", {key: getattr(self, key) for key in ("chat_provider", "chat_model", "embedding_provider", "embedding_model")})

    def _default_chat_model(self) -> str:
        if self.chat_provider == "ollama":
            return settings.ollama_chat_model
        if self.chat_provider == "deepseek":
            return settings.deepseek_chat_model
        return settings.openai_chat_model


runtime_config = RuntimeConfig()
