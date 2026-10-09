from mcp.server import MCPServer
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SHIPPING_MCP_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = Field(default=8003, ge=1, le=65535)


mcp = MCPServer("BridgeCart Shipping", instructions="No shipping tools are available yet.")


def main() -> None:
    settings = Settings()
    mcp.run(transport="streamable-http", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
