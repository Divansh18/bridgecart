from mcp.server import MCPServer
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INVENTORY_MCP_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = Field(default=8002, ge=1, le=65535)


mcp = MCPServer("BridgeCart Inventory", instructions="No inventory tools are available yet.")


def main() -> None:
    settings = Settings()
    mcp.run(transport="streamable-http", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
