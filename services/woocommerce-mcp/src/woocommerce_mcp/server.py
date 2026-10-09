from mcp.server import MCPServer

from woocommerce_mcp.config import Settings

mcp = MCPServer("BridgeCart WooCommerce", instructions="No WooCommerce tools are available yet.")


def main() -> None:
    settings = Settings()
    mcp.run(transport="streamable-http", host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
