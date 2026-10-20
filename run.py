#!/usr/bin/env python3
"""BizReady entry point.

    python run.py                 # http://localhost:8000
    python run.py --port 8080
    python run.py --reset         # back up and rebuild the demo database

Environment:
    BIZREADY_DATA_DIR        override the data directory
    BIZREADY_AI_KEY          enable live AI coaching (server-side only)
    BIZREADY_SECURE_COOKIES  set to 1 behind HTTPS
"""

import argparse
import sys

from server import config
from server.ai import ai_status
from server.db import init_db, reset_database
from server.http import make_server


def main(argv=None):
    parser = argparse.ArgumentParser(description="BizReady server")
    parser.add_argument("--host", default=config.HOST, help="bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=config.PORT, help="port (default 8000, 0 = random)")
    parser.add_argument("--reset", action="store_true", help="back up and recreate the database")
    args = parser.parse_args(argv)

    if args.reset:
        reset_database()
        print("Database reset. A backup was written to data/backups/.")

    init_db()
    server = make_server(args.host, args.port)
    host, port = server.server_address[0], server.server_address[1]
    print(f"\n  BizReady is running at http://{host}:{port}\n")
    print("  Demo learner : aina@demo.bizready.app / Demo1234!")
    print("  Admin        : admin@bizready.app / Admin1234!")
    print("  AI coach     : " + ("live API configured" if ai_status()["configured"] else "DEMO MODE (no API key configured)") + "\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
