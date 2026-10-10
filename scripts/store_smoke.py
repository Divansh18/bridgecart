"""Smoke check the local ingress without changing system DNS or store data."""

from http.client import HTTPConnection

HOST = "shop.bridgecart.local:8088"
CHECKS = [
    ("/", 200, "BridgeCart Demo Store"),
    ("/product/bridgecart-demo-mug/", 200, "BridgeCart Demo Mug"),
    ("/cart/", 200, "Cart"),
    ("/checkout/", 302, "/cart/"),
    ("/wp-login.php", 200, "Log In"),
]


def main() -> None:
    for path, expected_status, expected in CHECKS:
        connection = HTTPConnection("127.0.0.1", 8088, timeout=15)
        connection.request("GET", path, headers={"Host": HOST})
        response = connection.getresponse()
        body = response.read().decode("utf-8", errors="replace")
        connection.close()
        content = response.getheader("Location", "") if response.status == 302 else body
        if response.status != expected_status or expected.lower() not in content.lower():
            raise RuntimeError(f"{path}: HTTP {response.status}; expected {expected_status} and {expected!r}")
        print(f"{path}: HTTP {response.status}")


if __name__ == "__main__":
    main()
