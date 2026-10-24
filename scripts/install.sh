#!/usr/bin/env bash
# ==============================================================================
# Frankenstein Storage - 1-Line Terminal Installer for macOS & Linux
# ==============================================================================
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/shivanggupta1931/Frankenstein-Storage/main/scripts/install.sh | bash
# Or locally:
#   bash scripts/install.sh
# ==============================================================================

set -e

# ANSI Color codes
BOLD="\033[1m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
RESET="\033[0m"

echo -e "${CYAN}${BOLD}"
echo "======================================================================"
echo "  🧟 Frankenstein Storage - Pooled Encrypted Redundant Storage Engine "
echo "======================================================================"
echo -e "${RESET}"

# 1. OS Detection
OS="$(uname -s)"
case "${OS}" in
    Darwin*)    PLATFORM="macOS" ;;
    Linux*)     PLATFORM="Linux" ;;
    *)          echo -e "${RED}Error: Unsupported operating system: ${OS}. Frankenstein Storage installer supports macOS and Linux.${RESET}"; exit 1 ;;
esac
echo -e "${GREEN}✓ Detected platform:${RESET} ${PLATFORM}"

# 2. Python 3 Check (>= 3.10)
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PY_VER="$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
        MAJOR="$(echo "$PY_VER" | cut -d. -f1)"
        MINOR="$(echo "$PY_VER" | cut -d. -f2)"
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "${RED}Error: Python 3.10 or higher is required.${RESET}"
    if [ "$PLATFORM" = "macOS" ]; then
        echo -e "Install Python using Homebrew: ${BOLD}brew install python@3.12${RESET}"
    else
        echo -e "Install Python using apt: ${BOLD}sudo apt update && sudo apt install python3 python3-venv python3-pip${RESET}"
    fi
    exit 1
fi
echo -e "${GREEN}✓ Found Python:${RESET} $("$PYTHON" --version) at $(command -v "$PYTHON")"

# 3. Determine Installation Directory
REPO_URL="https://github.com/shivanggupta1931/Frankenstein-Storage.git"
if [ -f "pyproject.toml" ] && [ -d "backend" ]; then
    INSTALL_DIR="$(pwd)"
    echo -e "${GREEN}✓ Installing in current repository directory:${RESET} ${INSTALL_DIR}"
else
    INSTALL_DIR="${HOME}/.frankenstein-storage"
    echo -e "${CYAN}→ Installing to:${RESET} ${INSTALL_DIR}"
    if [ ! -d "$INSTALL_DIR" ]; then
        if ! command -v git >/dev/null 2>&1; then
            echo -e "${RED}Error: Git is required to clone the repository.${RESET}"
            exit 1
        fi
        echo -e "${CYAN}→ Cloning repository...${RESET}"
        git clone "$REPO_URL" "$INSTALL_DIR"
    else
        echo -e "${CYAN}→ Updating existing repository...${RESET}"
        cd "$INSTALL_DIR" && git pull || true
    fi
fi

cd "$INSTALL_DIR"

# 4. Create Virtual Environment
echo -e "${CYAN}→ Setting up Python virtual environment...${RESET}"
if [ ! -d ".venv" ]; then
    "$PYTHON" -m venv .venv
fi

VENV_PYTHON="${INSTALL_DIR}/.venv/bin/python"
VENV_PIP="${INSTALL_DIR}/.venv/bin/pip"

"$VENV_PIP" install --upgrade pip --quiet

# 5. Install Python Dependencies
echo -e "${CYAN}→ Installing backend dependencies...${RESET}"
if [ -f "requirements.txt" ]; then
    "$VENV_PIP" install -r requirements.txt --quiet
else
    "$VENV_PIP" install fastapi uvicorn pydantic cryptography python-multipart httpx --quiet
fi
echo -e "${GREEN}✓ Python dependencies installed.${RESET}"

# 6. Verify or Build Frontend
if [ ! -f "frontend/dist/index.html" ]; then
    echo -e "${YELLOW}Notice: Pre-built frontend dist not found. Checking for Node.js to build frontend...${RESET}"
    if command -v npm >/dev/null 2>&1; then
        echo -e "${CYAN}→ Building Vite frontend...${RESET}"
        (cd frontend && npm install --silent && npm run build)
        echo -e "${GREEN}✓ Frontend built successfully.${RESET}"
    else
        echo -e "${YELLOW}Warning: Node.js/npm not found. Backend will operate in headless API mode or use pre-compiled assets.${RESET}"
    fi
else
    echo -e "${GREEN}✓ Frontend static bundle verified.${RESET}"
fi

# 7. Generate Default Configuration & Auth Token if missing
if [ ! -f ".env" ]; then
    echo -e "${CYAN}→ Generating secure configuration (.env)...${RESET}"
    SECRET_TOKEN="$("$VENV_PYTHON" -c "import secrets; print(secrets.token_urlsafe(32))")"
    cat <<EOF > .env
HOST=127.0.0.1
PORT=8765
DATABASE_PATH=frankenstein.db
AUTH_TOKEN=${SECRET_TOKEN}
MIN_DRIVES=3
MIN_RESERVE_BYTES=2147483648
MIN_RESERVE_RATIO=0.05
EOF
    echo -e "${GREEN}✓ Created .env with generated session token.${RESET}"
fi

TOKEN="$(grep -E '^AUTH_TOKEN=' .env | cut -d= -f2- || echo 'frankenstein-demo-token')"

# 8. Create CLI Launcher
BIN_DIR="${HOME}/.local/bin"
mkdir -p "$BIN_DIR"
LAUNCHER="${BIN_DIR}/frankenstein"

cat <<EOF > "$LAUNCHER"
#!/usr/bin/env bash
cd "${INSTALL_DIR}"
exec "${VENV_PYTHON}" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8765 "\$@"
EOF
chmod +x "$LAUNCHER"

# Try symlinking to /usr/local/bin if writable
if [ -w "/usr/local/bin" ]; then
    ln -sf "$LAUNCHER" /usr/local/bin/frankenstein 2>/dev/null || true
fi

echo -e "\n${GREEN}${BOLD}======================================================================${RESET}"
echo -e "${GREEN}${BOLD}  🎉 Frankenstein Storage successfully installed!                     ${RESET}"
echo -e "${GREEN}${BOLD}======================================================================${RESET}"
echo -e "  Platform:        ${PLATFORM}"
echo -e "  Directory:       ${INSTALL_DIR}"
echo -e "  Web Dashboard:   ${CYAN}http://localhost:8765${RESET}"
echo -e "  Session Token:   ${YELLOW}${TOKEN}${RESET}"
echo -e "  CLI Launcher:    ${BOLD}${LAUNCHER}${RESET}"
echo -e "----------------------------------------------------------------------"
echo -e "To start the application now, run:"
echo -e "  ${BOLD}${INSTALL_DIR}/.venv/bin/uvicorn backend.app.main:app --port 8765${RESET}"
echo -e "Or simply:"
echo -e "  ${BOLD}frankenstein${RESET} (ensure ~/.local/bin is in your PATH)"
echo -e "======================================================================\n"
