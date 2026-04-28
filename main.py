from gateway.config import DEFAULT_GATEWAY_PORT
from gateway.server import start_server


if __name__ == "__main__":
    start_server(DEFAULT_GATEWAY_PORT)
