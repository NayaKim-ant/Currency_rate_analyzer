#!/usr/bin/env bash
# ==============================================================================
# Currency Rate Analyzer - Backend Setup & Launch Script (uv-based)
# ==============================================================================
# Usage:
#   ./setup.sh              # Create venv & install dependencies
#   ./setup.sh --run        # Setup (if needed) and run FastAPI backend server
#   ./setup.sh --ml         # Include optional ML dependencies (requirements-ml.txt)
#   ./setup.sh --recreate   # Recreate virtual environment from scratch
#   ./setup.sh --help       # Display help information
# ==============================================================================

set -euo pipefail

# Color codes for pretty terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Determine project and backend directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
BACKEND_DIR="$PROJECT_ROOT/project/backend"
VENV_DIR="$BACKEND_DIR/.venv"

# Options
RUN_SERVER=false
INSTALL_ML=false
RECREATE=false
RUN_MIGRATE=false
PYTHON_VERSION="3.11"

print_help() {
    cat << EOF
Currency Rate Analyzer - Backend Setup Script (uv)

Usage:
  ./setup.sh [OPTIONS]

Options:
  -r, --run          Set up (if needed) and start the FastAPI backend server
  -m, --ml           Install optional ML forecasting dependencies (requirements-ml.txt)
  -u, --upgrade      Upgrade all packages to latest compatible versions
  -p, --python <ver> Specify Python version for uv venv (default: 3.11)
  -f, --recreate     Remove and recreate the virtual environment (.venv)
  --migrate          Run Alembic database migrations (alembic upgrade head)
  -h, --help         Show this help message

Examples:
  ./setup.sh                 # Standard setup: venv + requirements-dev.txt
  ./setup.sh --run           # Set up environment and immediately start backend
  ./setup.sh --ml --run      # Set up with ML packages and start backend
EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -r|--run)
            RUN_SERVER=true
            shift
            ;;
        -m|--ml)
            INSTALL_ML=true
            shift
            ;;
        -f|--recreate)
            RECREATE=true
            shift
            ;;
        --migrate)
            RUN_MIGRATE=true
            shift
            ;;
        -p|--python)
            if [[ -n "${2:-}" ]]; then
                PYTHON_VERSION="$2"
                shift 2
            else
                echo -e "${RED}[ERROR] --python requires a version argument.${NC}"
                exit 1
            fi
            ;;
        -h|--help)
            print_help
            exit 0
            ;;
        *)
            echo -e "${RED}[ERROR] Unknown option: $1${NC}"
            print_help
            exit 1
            ;;
    esac
done

echo -e "${CYAN}================================================================${NC}"
echo -e "${CYAN}  Currency Rate Analyzer - Backend Setup (uv)                   ${NC}"
echo -e "${CYAN}================================================================${NC}"

# Ensure common paths are in PATH
for p in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    if [ -d "$p" ] && [[ ":$PATH:" != *":$p:"* ]]; then
        export PATH="$p:$PATH"
    fi
done

# Step 1: Ensure uv is installed
if ! command -v uv >/dev/null 2>&1; then
    echo -e "${YELLOW}[!] uv is not installed on this system.${NC}"
    echo -e "${CYAN}[*] Installing uv via official script (https://astral.sh/uv)...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

    if ! command -v uv >/dev/null 2>&1; then
        echo -e "${RED}[ERROR] Failed to automatically install uv. Please install it manually:${NC}"
        echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
        echo "  or: brew install uv"
        exit 1
    fi
fi

UV_VERSION="$(uv --version)"
echo -e "${GREEN}[✓] Using uv: ${UV_VERSION}${NC}"

# Step 2: Ensure .env exists in project/backend
if [ ! -f "$BACKEND_DIR/.env" ]; then
    if [ -f "$BACKEND_DIR/.env.example" ]; then
        echo -e "${YELLOW}[*] .env not found. Creating from .env.example...${NC}"
        cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
        echo -e "${GREEN}[✓] Created $BACKEND_DIR/.env${NC}"
    else
        echo -e "${YELLOW}[!] .env.example not found in $BACKEND_DIR.${NC}"
    fi
else
    echo -e "${GREEN}[✓] Backend .env file already exists.${NC}"
fi

# Step 3: Create or recreate virtual environment
if [ "$RECREATE" = true ] && [ -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}[*] Removing existing virtual environment at $VENV_DIR...${NC}"
    rm -rf "$VENV_DIR"
fi

if [ ! -d "$VENV_DIR" ]; then
    echo -e "${CYAN}[*] Creating virtual environment at $VENV_DIR (Python $PYTHON_VERSION)...${NC}"
    uv venv "$VENV_DIR" --python "$PYTHON_VERSION"
    echo -e "${GREEN}[✓] Virtual environment created successfully.${NC}"
else
    echo -e "${GREEN}[✓] Virtual environment already exists at $VENV_DIR.${NC}"
fi

# Step 4: Install dependencies
echo -e "${CYAN}[*] Installing backend dependencies (requirements-dev.txt)...${NC}"
uv pip install --python "$VENV_DIR" -r "$BACKEND_DIR/requirements-dev.txt"

if [ "$INSTALL_ML" = true ]; then
    echo -e "${CYAN}[*] Installing ML forecasting dependencies (requirements-ml.txt)...${NC}"
    uv pip install --python "$VENV_DIR" -r "$BACKEND_DIR/requirements-ml.txt"
fi

echo -e "${GREEN}[✓] All requested dependencies are installed.${NC}"

# Step 5: Optional Migration & Run Server
if [ "$RUN_MIGRATE" = true ]; then
    echo -e "${CYAN}[*] Applying database migrations (alembic upgrade head)...${NC}"
    (
        cd "$BACKEND_DIR"
        uv run --python "$VENV_DIR" alembic upgrade head
    ) || echo -e "${YELLOW}[!] Alembic migration failed. Please ensure PostgreSQL is running.${NC}"
fi

if [ "$RUN_SERVER" = true ]; then
    echo -e "${CYAN}================================================================${NC}"
    echo -e "${GREEN}[*] Starting FastAPI backend with uvicorn...${NC}"
    echo -e "${CYAN}    API URL: http://127.0.0.1:8000${NC}"
    echo -e "${CYAN}    Health check: http://127.0.0.1:8000/health${NC}"
    echo -e "${CYAN}================================================================${NC}"
    cd "$BACKEND_DIR"
    exec uv run --python "$VENV_DIR" uvicorn app.main:app --reload --reload-dir app
fi

# Completion Guide
echo -e "${CYAN}================================================================${NC}"
echo -e "${GREEN}[✓] Backend environment setup is complete!${NC}"
echo -e "${CYAN}================================================================${NC}"
echo -e "To start the backend immediately:"
echo -e "  ${YELLOW}./setup.sh --run${NC}"
echo -e ""
echo -e "Or activate the virtual environment manually:"
echo -e "  ${YELLOW}source project/backend/.venv/bin/activate${NC}"
echo -e "  ${YELLOW}cd project/backend${NC}"
echo -e "  ${YELLOW}alembic upgrade head${NC}               # (PostgreSQL required)"
echo -e "  ${YELLOW}uvicorn app.main:app --reload --reload-dir app${NC}"
echo -e "================================================================"
