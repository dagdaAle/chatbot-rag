"""Configurazione da variabili ambiente."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Impostazioni applicazione."""

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"
    
    # Provider LLM: "openai" o "ollama"
    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_base_url: str = ""  # Es: https://api.deepseek.com (vuoto = default OpenAI)
    openai_chat_model: str = "gpt-4o-mini"  # Default per chat
    openai_embedding_model: str = "text-embedding-3-small"  # Default per embedding
    
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
    """Configurazione runtime modificabile dall'utente (non persiste al riavvio).
    
    Chat e embedding hanno provider INDIPENDENTI:
    - Puoi usare Ollama per la chat e OpenAI per gli embedding (o viceversa).
    """

    def __init__(self) -> None:
        # Provider e modello per la CHAT
        self.chat_provider: str = settings.llm_provider
        self.chat_model: str = self._default_chat_model()
        
        # Provider e modello per gli EMBEDDING (indipendente dalla chat)
        self.embedding_provider: str = "openai"  # Default: OpenAI per embedding
        self.embedding_model: str = settings.openai_embedding_model

    def _default_chat_model(self) -> str:
        if self.chat_provider == "ollama":
            return settings.ollama_chat_model
        return settings.openai_chat_model


runtime_config = RuntimeConfig()
