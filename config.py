import os
from dataclasses import dataclass, field


def _load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


@dataclass
class AgentConfig:
    """Agent configuration loaded from environment variables."""

    AGENT_VERSION: str = "1.0.8"

    LOCAL_MODEL_URI: str = field(
        default_factory=lambda: os.getenv(
            "LOCAL_MODEL_URI", "ws://192.168.31.43:8000/ws/navigate"
        )
    )

    # Supported values: local_ws | openai_compatible
    LLM_BACKEND: str = field(
        default_factory=lambda: os.getenv("LLM_BACKEND", "local_ws")
    )

    OPENAI_API_KEY: str = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY", "0")
    )
    OPENAI_BASE_URL: str = field(
        default_factory=lambda: os.getenv(
            "OPENAI_BASE_URL", "http://192.168.31.43:9000/v1"
        )
    )
    OPENAI_MODEL: str = field(
        default_factory=lambda: os.getenv(
            "OPENAI_MODEL", "Qwen3-VL-30B-A3B-Instruct"
        )
    )

    USB_SERIAL_PORT: str = field(
        default_factory=lambda: os.getenv("USB_SERIAL_PORT", "/dev/ttyACM0")
    )
    USB_SERIAL_BAUDRATE: int = field(
        default_factory=lambda: int(os.getenv("USB_SERIAL_BAUDRATE", "115200"))
    )

    DB_PATH: str = field(
        default_factory=lambda: os.getenv("DB_PATH", "history.db")
    )
    ASM_JSON_PATH: str = field(
        default_factory=lambda: os.getenv("ASM_JSON_PATH", "asm_data.json")
    )
    VIDEO_BASE_DIR: str = field(
        default_factory=lambda: os.getenv("VIDEO_BASE_DIR", "videos")
    )

    WEBSOCKET_HOST: str = field(
        default_factory=lambda: os.getenv("WEBSOCKET_HOST", "127.0.0.1")
    )
    WEBSOCKET_PORT: int = field(
        default_factory=lambda: int(os.getenv("WEBSOCKET_PORT", "8766"))
    )

    WELCOME_POSITION_FILE: str = field(
        default_factory=lambda: os.getenv(
            "WELCOME_POSITION_FILE", "/home/sunrise/welcome_position.txt"
        )
    )

    USB_SERIAL_ENABLED: bool = field(
        default_factory=lambda: os.getenv(
            "USB_SERIAL_ENABLED", "false"
        ).lower()
        in ("true", "1", "yes")
    )

    MAX_REACT_ITERATIONS: int = 8
    AGENT_MEMORY_SIZE: int = 50


config = AgentConfig()
