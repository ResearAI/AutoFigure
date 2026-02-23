#!/bin/bash
#
# AutoFigure - One-Click Start Script
# Starts both backend and frontend servers for local development
#
# Usage: ./start.sh [-f]
#   -f  Force mode: automatically kill any processes using required ports
#
# IMPORTANT: This application runs on localhost only.
# Public network access is disabled for security.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
FORCE_MODE=false
while getopts "f" opt; do
    case $opt in
        f) FORCE_MODE=true ;;
        *) echo "Usage: $0 [-f]"; exit 1 ;;
    esac
done

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

# Log file locations
BACKEND_LOG="/tmp/autofigure_backend.log"
FRONTEND_LOG="/tmp/autofigure_frontend.log"

# Port configuration
BACKEND_PORT=8796
FRONTEND_PORT=6002

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  AutoFigure - Local Development Server ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to get PIDs using a port (uses multiple methods for reliability)
get_port_pids() {
    local port=$1
    local pids=""

    # Try fuser first (most reliable)
    if command -v fuser &> /dev/null; then
        pids=$(fuser ${port}/tcp 2>/dev/null | tr -s ' ' '\n' | grep -E '^[0-9]+$' | tr '\n' ' ')
    fi

    # Fallback to lsof
    if [ -z "$pids" ] && command -v lsof &> /dev/null; then
        pids=$(lsof -t -i :$port 2>/dev/null | tr '\n' ' ')
    fi

    # Fallback to ss + ps
    if [ -z "$pids" ]; then
        pids=$(ss -tlnp 2>/dev/null | grep ":${port} " | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | tr '\n' ' ')
    fi

    echo "$pids"
}

# Function to check if a port is in use
check_port() {
    local port=$1
    local pids=$(get_port_pids $port)
    if [ -n "$pids" ]; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

# Function to kill process on a port
kill_port() {
    local port=$1
    local pids=$(get_port_pids $port)
    if [ -n "$pids" ]; then
        echo -e "${YELLOW}Stopping existing process(es) on port $port (PIDs: $pids)${NC}"
        # First try graceful termination
        echo "$pids" | xargs -r kill 2>/dev/null || true
        sleep 2
        # Check if still running and force kill if necessary
        local remaining=$(get_port_pids $port)
        if [ -n "$remaining" ]; then
            echo -e "${YELLOW}Force killing remaining process(es) on port $port${NC}"
            echo "$remaining" | xargs -r kill -9 2>/dev/null || true
            sleep 1
        fi
    fi
}

# Check and free ports if needed
if check_port $BACKEND_PORT; then
    echo -e "${YELLOW}Port $BACKEND_PORT is in use.${NC}"
    if [ "$FORCE_MODE" = true ]; then
        echo -e "${YELLOW}Force mode: killing existing process...${NC}"
        kill_port $BACKEND_PORT
    else
        read -p "Kill existing process? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            kill_port $BACKEND_PORT
        else
            echo -e "${RED}Please free port $BACKEND_PORT and try again.${NC}"
            exit 1
        fi
    fi
fi

if check_port $FRONTEND_PORT; then
    echo -e "${YELLOW}Port $FRONTEND_PORT is in use.${NC}"
    if [ "$FORCE_MODE" = true ]; then
        echo -e "${YELLOW}Force mode: killing existing process...${NC}"
        kill_port $FRONTEND_PORT
    else
        read -p "Kill existing process? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            kill_port $FRONTEND_PORT
        else
            echo -e "${RED}Please free port $FRONTEND_PORT and try again.${NC}"
            exit 1
        fi
    fi
fi

# Check Python
if command -v python3 &> /dev/null && python3 --version 2>&1 | grep -q "Python 3"; then
    PYTHON=python3
elif command -v python &> /dev/null && python --version 2>&1 | grep -q "Python 3"; then
    PYTHON=python
elif command -v py &> /dev/null && py --version 2>&1 | grep -q "Python 3"; then
    PYTHON=py
else
    echo -e "${RED}Error: Python 3 is not installed.${NC}"
    exit 1
fi

# Check Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}Error: Node.js is not installed.${NC}"
    exit 1
fi

# Check npm
if ! command -v npm &> /dev/null; then
    echo -e "${RED}Error: npm is not installed.${NC}"
    exit 1
fi

echo -e "${GREEN}Environment checks passed.${NC}"
echo ""

# Install backend dependencies if needed
echo -e "${BLUE}[1/4] Checking backend dependencies...${NC}"
cd "$BACKEND_DIR"
if [ -f "requirements.txt" ]; then
    pip install -q -r requirements.txt 2>/dev/null || {
        echo -e "${YELLOW}Installing backend dependencies...${NC}"
        pip install -r requirements.txt
    }
fi
echo -e "${GREEN}Backend dependencies ready.${NC}"

# Install frontend dependencies if needed
echo -e "${BLUE}[2/4] Checking frontend dependencies...${NC}"
cd "$FRONTEND_DIR"
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}Installing frontend dependencies (this may take a while)...${NC}"
    npm install
fi
echo -e "${GREEN}Frontend dependencies ready.${NC}"

# Start backend
echo -e "${BLUE}[3/4] Starting backend server...${NC}"
cd "$BACKEND_DIR"
nohup $PYTHON app.py > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
echo -e "${GREEN}Backend started (PID: $BACKEND_PID)${NC}"
echo -e "  Log: $BACKEND_LOG"

# Wait for backend to be ready
echo -n "  Waiting for backend..."
for i in {1..30}; do
    if curl -s http://127.0.0.1:$BACKEND_PORT/health > /dev/null 2>&1; then
        echo -e " ${GREEN}Ready!${NC}"
        break
    fi
    echo -n "."
    sleep 1
done

# Start frontend
echo -e "${BLUE}[4/4] Starting frontend server...${NC}"
cd "$FRONTEND_DIR"
nohup npm run dev > "$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!
echo -e "${GREEN}Frontend started (PID: $FRONTEND_PID)${NC}"
echo -e "  Log: $FRONTEND_LOG"

# Wait for frontend to be ready
echo -n "  Waiting for frontend..."
sleep 3
for i in {1..30}; do
    if curl -s http://127.0.0.1:$FRONTEND_PORT > /dev/null 2>&1; then
        echo -e " ${GREEN}Ready!${NC}"
        break
    fi
    echo -n "."
    sleep 1
done

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  AutoFigure is running!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  ${BLUE}Frontend:${NC} http://127.0.0.1:$FRONTEND_PORT"
echo -e "  ${BLUE}Backend:${NC}  http://127.0.0.1:$BACKEND_PORT"
echo ""
echo -e "  ${YELLOW}Note: This application runs on localhost only.${NC}"
echo -e "  ${YELLOW}Public network access is disabled for security.${NC}"
echo ""
echo -e "  To stop the servers:"
echo -e "    kill $BACKEND_PID $FRONTEND_PID"
echo -e "  Or run:"
echo -e "    ./stop.sh"
echo ""
echo -e "  Logs:"
echo -e "    Backend:  tail -f $BACKEND_LOG"
echo -e "    Frontend: tail -f $FRONTEND_LOG"
echo ""

# Save PIDs for stop script
echo "$BACKEND_PID" > /tmp/autofigure_backend.pid
echo "$FRONTEND_PID" > /tmp/autofigure_frontend.pid
