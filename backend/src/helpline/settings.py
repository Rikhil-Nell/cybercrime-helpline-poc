from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    sip_outbound_trunk_id: str = "ST_EdhhfeXqDent"
    twilio_number: str = "+19129375928"
    openai_api_key: str = ""
    deepgram_api_key: str = ""
    database_url: str = "postgresql+asyncpg://helpline:helpline@127.0.0.1:5433/helpline"
    agent_name: str = "helpline"
    # Optional TURN-only ICE. Off by default — Call_Bot works without it on this machine.
    livekit_ice_relay: bool = False
    upload_dir: Path = Path(__file__).resolve().parents[3] / "data" / "uploads"


settings = Settings()
