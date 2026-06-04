#!/bin/bash
# start.sh — requires Git Bash or WSL on Windows
set -e

export SEC_EDGAR_USER_AGENT="StockPortfolioAgent/1.0 (research@example.com)"

echo "Starting MCP servers..."
uvx sec-edgar-mcp &
SEC_EDGAR_PID=$!
uvx edinet-mcp &
EDINET_PID=$!

sleep 3

echo "Starting backend..."
venv/Scripts/python backend/main.py &
BACKEND_PID=$!

echo "Starting frontend..."
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "============================================"
echo "  System starting:"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo "  API docs: http://localhost:8000/docs"
echo "============================================"
echo ""

cleanup() {
    echo "Shutting down..."
    kill $FRONTEND_PID 2>/dev/null
    kill $BACKEND_PID 2>/dev/null
    kill $EDINET_PID 2>/dev/null
    kill $SEC_EDGAR_PID 2>/dev/null
    wait
}
trap cleanup EXIT INT TERM

wait