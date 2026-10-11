"""Read-only dashboard routing smoke check; never reads credentials."""
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:8088"


def fetch(path: str) -> tuple[int, str]:
    try:
        with urlopen(Request(BASE + path, headers={"Cache-Control": "no-cache", "Host": "app.bridgecart.local"}), timeout=8) as response:
            return response.status, response.read(200_000).decode()
    except HTTPError as error:
        return error.code, error.read(200_000).decode()


def main() -> None:
    home_status, home = fetch("/")
    deep_status, deep = fetch("/servers")
    keys_status, keys_page = fetch("/api-keys")
    config_status, config = fetch("/config.js")
    api_status, api = fetch("/api/auth/me")
    assert home_status == 200 and '<div id="root"></div>' in home
    assert deep_status == 200 and '<div id="root"></div>' in deep
    assert keys_status == 200 and '<div id="root"></div>' in keys_page
    assert config_status == 200 and "http://api.bridgecart.local:8088/mcp" in config
    assert api_status == 401 and "Authentication required" in api
    print("Dashboard root, SPA routes, runtime MCP URL, and unauthenticated API routing: passed")


if __name__ == "__main__":
    main()
