#!/usr/bin/env python3
"""
Run the Bank Reconciliation API server.

Usage:
    python run_server.py [--port PORT] [--reload]

The server will be available at http://localhost:8000
API docs at http://localhost:8000/docs
"""
import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Run the Bank Reconciliation API server")
    parser.add_argument("--port", type=int, default=8000, help="Port to run on (default: 8000)")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           Bank Reconciliation API Server                      ║
╠══════════════════════════════════════════════════════════════╣
║  API:      http://localhost:{args.port}                           ║
║  Docs:     http://localhost:{args.port}/docs                      ║
║  Frontend: http://localhost:5173 (run 'npm run dev' in frontend) ║
╚══════════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "src.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload
    )


if __name__ == "__main__":
    main()
