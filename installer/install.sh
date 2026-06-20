#!/usr/bin/env bash
# Vectrola Installer - Multimodal Music Knowledge Graph
# Usage: curl -fsSL https://raw.githubusercontent.com/Arunes007/vectrola/main/installer/install.sh | bash
#        curl -fsSL ... | bash -s -- --non-interactive --llm=local --qdrant=hosted

set -euo pipefail

# ============================================================================
# Configuration
# ============================================================================

VECTROLA_VERSION="${VECTROLA_VERSION:-main}"
VECTROLA_REPO="https://github.com/Arunes007/vectrola"
VECTROLA_INSTALL_DIR="${VECTROLA_INSTALL_DIR:-$HOME/.vectrola}"
VECTROLA_CONFIG_DIR="${VECTROLA_CONFIG_DIR:-$HOME/.config/vectrola}"

# Default service URLs
DEFAULT_OLLAMA_HOST="http://localhost:11434"
DEFAULT_QDRANT_HOSTED="https://qdrant-vectrola.up.railway.app"
DEFAULT_QDRANT_LOCAL="http://localhost:6333"

# ============================================================================
# Colors and Output
# ============================================================================

setup_colors() {
    if [[ -t 1 ]] && command -v tput >/dev/null 2>&1; then
        RED=$(tput setaf 1)
        GREEN=$(tput setaf 2)
        YELLOW=$(tput setaf 3)
        BLUE=$(tput setaf 4)
        MAGENTA=$(tput setaf 5)
        CYAN=$(tput setaf 6)
        BOLD=$(tput bold)
        DIM=$(tput dim)
        RESET=$(tput sgr0)
    else
        RED="" GREEN="" YELLOW="" BLUE="" MAGENTA="" CYAN="" BOLD="" DIM="" RESET=""
    fi
}

info()    { echo "${BLUE}ℹ${RESET} $*"; }
success() { echo "${GREEN}✓${RESET} $*"; }
warn()    { echo "${YELLOW}⚠${RESET} $*"; }
error()   { echo "${RED}✗${RESET} $*" >&2; }
step()    { echo "${MAGENTA}→${RESET} $*"; }

print_header() {
    echo ""
    echo "${BOLD}🎧 Vectrola Installer${RESET}"
    echo "   ${DIM}Multimodal Music Knowledge Graph${RESET}"
    echo ""
}

print_separator() {
    echo "${DIM}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
}

# ============================================================================
# Platform Detection
# ============================================================================

detect_platform() {
    local os arch
    os=$(uname -s)
    arch=$(uname -m)

    case "$os" in
        Darwin)
            PLATFORM="macos"
            # Detect Apple Silicon running under Rosetta
            if [[ "$arch" == "x86_64" ]]; then
                if sysctl -n sysctl.proc_translated 2>/dev/null | grep -q 1; then
                    arch="arm64"
                fi
            fi
            ;;
        Linux)
            PLATFORM="linux"
            case "$arch" in
                aarch64) arch="arm64" ;;
            esac
            ;;
        MINGW*|MSYS*|CYGWIN*)
            error "For Windows, use PowerShell:"
            echo "  ${CYAN}irm https://raw.githubusercontent.com/Arunes007/vectrola/main/installer/install.ps1 | iex${RESET}"
            exit 1
            ;;
        *)
            error "Unsupported operating system: $os"
            exit 1
            ;;
    esac

    ARCH="$arch"
    success "Platform: $PLATFORM ($ARCH)"
}

# ============================================================================
# Prerequisite Checks
# ============================================================================

check_git() {
    if ! command -v git >/dev/null 2>&1; then
        error "Git is required but not installed"
        echo ""
        case "$PLATFORM" in
            macos)
                echo "  Install with: ${CYAN}xcode-select --install${RESET}"
                echo "  Or:           ${CYAN}brew install git${RESET}"
                ;;
            linux)
                echo "  Install with: ${CYAN}sudo apt install git${RESET}  (Debian/Ubuntu)"
                echo "                ${CYAN}sudo dnf install git${RESET}  (Fedora)"
                echo "                ${CYAN}sudo pacman -S git${RESET}   (Arch)"
                ;;
        esac
        exit 1
    fi

    local version
    version=$(git --version | grep -oE '[0-9]+\.[0-9]+' | head -1)
    success "Git $version found"
}

check_python() {
    local min_version="3.10"
    local cmd version

    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")

            if [[ "$(printf '%s\n' "$min_version" "$version" | sort -V | head -1)" == "$min_version" ]]; then
                PYTHON_CMD="$cmd"
                PYTHON_VERSION="$version"
                success "Python $version found"
                return 0
            fi
        fi
    done

    error "Python 3.10+ is required"
    echo ""
    case "$PLATFORM" in
        macos)
            echo "  Install with: ${CYAN}brew install python@3.11${RESET}"
            echo "  Or download:  https://www.python.org/downloads/"
            ;;
        linux)
            echo "  Install with: ${CYAN}sudo apt install python3.11 python3.11-venv${RESET}  (Debian/Ubuntu)"
            echo "                ${CYAN}sudo dnf install python3.11${RESET}  (Fedora)"
            echo "                ${CYAN}sudo pacman -S python${RESET}   (Arch)"
            ;;
    esac
    exit 1
}

check_ollama() {
    if command -v ollama >/dev/null 2>&1; then
        # Check if Ollama is running
        if curl -s --connect-timeout 2 "$DEFAULT_OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
            success "Ollama is installed and running"
            OLLAMA_AVAILABLE=true
            OLLAMA_RUNNING=true
        else
            warn "Ollama is installed but not running"
            OLLAMA_AVAILABLE=true
            OLLAMA_RUNNING=false
        fi
    else
        info "Ollama not found (needed for local LLM)"
        OLLAMA_AVAILABLE=false
        OLLAMA_RUNNING=false
    fi
}

check_docker() {
    if command -v docker >/dev/null 2>&1; then
        if docker info >/dev/null 2>&1; then
            # Check for running Qdrant container
            if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^qdrant$'; then
                success "Docker available, Qdrant container running"
                DOCKER_AVAILABLE=true
                QDRANT_RUNNING=true
            else
                success "Docker available"
                DOCKER_AVAILABLE=true
                QDRANT_RUNNING=false
            fi
        else
            info "Docker installed but daemon not running"
            DOCKER_AVAILABLE=false
            QDRANT_RUNNING=false
        fi
    else
        info "Docker not found (needed for local Qdrant)"
        DOCKER_AVAILABLE=false
        QDRANT_RUNNING=false
    fi
}

# ============================================================================
# Interactive Configuration
# ============================================================================

prompt_llm_config() {
    echo ""
    print_separator
    echo "${BOLD}                    CONFIGURATION${RESET}"
    print_separator
    echo ""

    echo "${BOLD}1. LLM for Semantic Analysis${RESET}"
    echo "   ${DIM}Vectrola uses an LLM to extract themes, moods, and narratives.${RESET}"
    echo ""
    echo "   ${CYAN}[1]${RESET} Local Ollama ${DIM}(recommended - private, no API costs)${RESET}"
    echo "   ${CYAN}[2]${RESET} Remote LLM endpoint ${DIM}(bring your own URL)${RESET}"
    echo ""

    local choice
    read -rp "   Choice [1]: " choice </dev/tty
    choice="${choice:-1}"

    case "$choice" in
        1)
            LLM_TYPE="local"
            OLLAMA_HOST="$DEFAULT_OLLAMA_HOST"

            # Offer to install Ollama if not present
            if [[ "$OLLAMA_AVAILABLE" != "true" ]]; then
                echo ""
                info "Ollama is not installed on your system"
                local install_ollama
                read -rp "   Install Ollama now? [Y/n]: " install_ollama </dev/tty
                install_ollama="${install_ollama:-Y}"

                if [[ "$install_ollama" =~ ^[Yy]$ ]]; then
                    INSTALL_OLLAMA=true
                else
                    warn "You'll need to install Ollama manually later"
                    INSTALL_OLLAMA=false
                fi
            fi
            ;;
        2)
            LLM_TYPE="remote"
            read -rp "   Enter LLM endpoint URL: " OLLAMA_HOST </dev/tty
            if [[ -z "$OLLAMA_HOST" ]]; then
                error "URL cannot be empty"
                exit 1
            fi
            ;;
        *)
            error "Invalid choice: $choice"
            exit 1
            ;;
    esac
}

prompt_qdrant_config() {
    echo ""
    echo "${BOLD}2. Vector Database ${DIM}(for semantic search)${RESET}"
    echo "   ${DIM}Store and search music embeddings.${RESET}"
    echo ""
    echo "   ${CYAN}[1]${RESET} Hosted Qdrant ${DIM}(easy start - no Docker needed)${RESET}"
    echo "   ${CYAN}[2]${RESET} Local Qdrant via Docker"
    echo "   ${CYAN}[3]${RESET} Remote Qdrant ${DIM}(bring your own URL)${RESET}"
    echo ""

    local choice
    read -rp "   Choice [1]: " choice </dev/tty
    choice="${choice:-1}"

    case "$choice" in
        1)
            QDRANT_TYPE="hosted"
            QDRANT_URL="$DEFAULT_QDRANT_HOSTED"
            ;;
        2)
            QDRANT_TYPE="local"
            QDRANT_URL="$DEFAULT_QDRANT_LOCAL"
            ;;
        3)
            QDRANT_TYPE="remote"
            read -rp "   Enter Qdrant URL: " QDRANT_URL </dev/tty
            if [[ -z "$QDRANT_URL" ]]; then
                error "URL cannot be empty"
                exit 1
            fi
            read -rp "   Enter Qdrant API key (or press Enter to skip): " QDRANT_API_KEY </dev/tty
            ;;
        *)
            error "Invalid choice: $choice"
            exit 1
            ;;
    esac
}

confirm_config() {
    echo ""
    print_separator
    echo ""
    echo "${BOLD}Installing with configuration:${RESET}"
    echo ""

    if [[ "$LLM_TYPE" == "local" ]]; then
        echo "  • LLM: ${CYAN}Local Ollama${RESET} ($OLLAMA_HOST)"
    else
        echo "  • LLM: ${CYAN}Remote${RESET} ($OLLAMA_HOST)"
    fi

    case "$QDRANT_TYPE" in
        hosted)
            echo "  • Qdrant: ${CYAN}Hosted${RESET} ($QDRANT_URL)"
            ;;
        local)
            echo "  • Qdrant: ${CYAN}Local Docker${RESET} ($QDRANT_URL)"
            ;;
        remote)
            echo "  • Qdrant: ${CYAN}Remote${RESET} ($QDRANT_URL)"
            ;;
    esac

    echo ""

    local confirm
    read -rp "Proceed? [Y/n]: " confirm </dev/tty
    confirm="${confirm:-Y}"

    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi
}

# ============================================================================
# Installation Functions
# ============================================================================

clone_repo() {
    step "Cloning Vectrola..."

    if [[ -d "$VECTROLA_INSTALL_DIR" ]]; then
        info "Existing installation found, updating..."
        cd "$VECTROLA_INSTALL_DIR"
        git fetch origin "$VECTROLA_VERSION" --depth 1 2>/dev/null || true
        git reset --hard "origin/$VECTROLA_VERSION" 2>/dev/null || git reset --hard "$VECTROLA_VERSION"
    else
        git clone --depth 1 --branch "$VECTROLA_VERSION" "$VECTROLA_REPO" "$VECTROLA_INSTALL_DIR"
    fi

    cd "$VECTROLA_INSTALL_DIR"
    success "Source code ready at $VECTROLA_INSTALL_DIR"
}

setup_venv() {
    step "Setting up Python environment..."

    local venv_dir="$VECTROLA_INSTALL_DIR/.venv"

    if [[ -d "$venv_dir" ]]; then
        # Check if existing venv is compatible
        if ! "$venv_dir/bin/python" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
            warn "Existing venv has incompatible Python, recreating..."
            rm -rf "$venv_dir"
        fi
    fi

    if [[ ! -d "$venv_dir" ]]; then
        "$PYTHON_CMD" -m venv "$venv_dir" || {
            error "Failed to create virtual environment"
            echo ""
            echo "  You may need to install venv:"
            case "$PLATFORM" in
                linux)
                    echo "    ${CYAN}sudo apt install python3-venv${RESET}  (Debian/Ubuntu)"
                    ;;
            esac
            exit 1
        }
    fi

    # shellcheck source=/dev/null
    source "$venv_dir/bin/activate"
    success "Virtual environment ready"
}

install_deps() {
    step "Installing dependencies..."

    # Check if vectrola is already installed
    if pip show vectrola >/dev/null 2>&1; then
        local installed_version
        installed_version=$(pip show vectrola 2>/dev/null | grep "^Version:" | awk '{print $2}')
        info "Vectrola already installed (version: ${installed_version:-unknown})"

        # In non-interactive mode, always reinstall to ensure latest
        if [[ "$NON_INTERACTIVE" == "true" ]]; then
            info "Non-interactive mode: updating installation..."
        else
            # Ask if user wants to reinstall/update
            local reinstall
            read -rp "   Reinstall dependencies? [y/N]: " reinstall </dev/tty
            reinstall="${reinstall:-N}"

            if [[ ! "$reinstall" =~ ^[Yy]$ ]]; then
                success "Using existing installation"
                return 0
            fi
        fi
    fi

    pip install --upgrade pip --quiet
    pip install -e ".[full]" --quiet

    success "Dependencies installed"
}

write_config() {
    step "Writing configuration..."

    mkdir -p "$VECTROLA_CONFIG_DIR"

    # Write config.json (used by vectrola CLI)
    local storage_mode
    case "$QDRANT_TYPE" in
        hosted|remote) storage_mode="remote" ;;
        local) storage_mode="local" ;;
    esac

    local config_json="$VECTROLA_CONFIG_DIR/config.json"
    cat > "$config_json" << EOF
{
  "version": 1,
  "storage": {
    "mode": "$storage_mode",
    "qdrant_url": "$QDRANT_URL",
    "qdrant_api_key": ${QDRANT_API_KEY:+\"$QDRANT_API_KEY\"}${QDRANT_API_KEY:-null}
  },
  "llm": {
    "provider": "ollama",
    "model": "llama3.2:1b",
    "api_key": null
  },
  "gdrive": {
    "enabled": false
  },
  "user": {
    "mode": "anonymous",
    "multi_tenant": false
  }
}
EOF

    # Also write .env for backwards compatibility
    local env_file="$VECTROLA_CONFIG_DIR/.env"

    cat > "$env_file" << EOF
# Generated by Vectrola installer on $(date)
# Edit this file to change your configuration

# LLM Configuration
OLLAMA_HOST=$OLLAMA_HOST

# Vector Database Configuration
QDRANT_URL=$QDRANT_URL
EOF

    if [[ -n "${QDRANT_API_KEY:-}" ]]; then
        echo "QDRANT_API_KEY=$QDRANT_API_KEY" >> "$env_file"
    fi

    success "Configuration saved to $config_json"
}

configure_shell() {
    step "Configuring shell..."

    local venv_bin="$VECTROLA_INSTALL_DIR/.venv/bin"
    local shell_name
    shell_name=$(basename "${SHELL:-/bin/bash}")

    local shell_rc=""
    case "$shell_name" in
        bash)
            if [[ "$PLATFORM" == "macos" ]]; then
                shell_rc="$HOME/.bash_profile"
            else
                shell_rc="$HOME/.bashrc"
            fi
            ;;
        zsh)
            shell_rc="$HOME/.zshrc"
            ;;
        fish)
            shell_rc="$HOME/.config/fish/config.fish"
            ;;
    esac

    if [[ -z "$shell_rc" ]]; then
        warn "Unknown shell: $shell_name"
        echo "  Add to your shell config: ${CYAN}export PATH=\"$venv_bin:\$PATH\"${RESET}"
        return
    fi

    local marker="# Vectrola"

    # Check if already configured
    if [[ -f "$shell_rc" ]] && grep -q "$marker" "$shell_rc" 2>/dev/null; then
        info "Shell already configured in $shell_rc"
        return
    fi

    # Add to shell config
    if [[ "$shell_name" == "fish" ]]; then
        mkdir -p "$(dirname "$shell_rc")"
        {
            echo ""
            echo "$marker"
            echo "fish_add_path \"$venv_bin\""
        } >> "$shell_rc"
    else
        {
            echo ""
            echo "$marker"
            echo "export PATH=\"$venv_bin:\$PATH\""
        } >> "$shell_rc"
    fi

    success "Added Vectrola to PATH in $shell_rc"
}

setup_local_qdrant() {
    if [[ "$QDRANT_TYPE" != "local" ]]; then
        return
    fi

    step "Setting up local Qdrant..."

    if [[ "$DOCKER_AVAILABLE" != "true" ]]; then
        warn "Docker not available - cannot start local Qdrant"
        echo ""
        echo "  Install Docker from: ${CYAN}https://docker.com/get-docker${RESET}"
        echo "  Then run: ${CYAN}docker run -d --name qdrant -p 6333:6333 qdrant/qdrant${RESET}"
        return
    fi

    if [[ "$QDRANT_RUNNING" == "true" ]]; then
        success "Qdrant container already running"
        return
    fi

    # Check if container exists but stopped
    if docker ps -a --format '{{.Names}}' | grep -q '^qdrant$'; then
        info "Starting existing Qdrant container..."
        docker start qdrant
    else
        info "Creating Qdrant container..."
        docker run -d \
            --name qdrant \
            -p 6333:6333 \
            -v "$VECTROLA_CONFIG_DIR/qdrant:/qdrant/storage" \
            qdrant/qdrant
    fi

    success "Qdrant container started"
}

install_ollama() {
    if [[ "${INSTALL_OLLAMA:-false}" != "true" ]]; then
        return
    fi

    step "Installing Ollama..."

    case "$PLATFORM" in
        macos)
            # Check if Homebrew is available
            if command -v brew >/dev/null 2>&1; then
                info "Installing via Homebrew..."
                brew install ollama
            else
                info "Downloading Ollama installer..."
                curl -fsSL https://ollama.ai/install.sh | sh
            fi
            ;;
        linux)
            info "Downloading Ollama installer..."
            curl -fsSL https://ollama.ai/install.sh | sh
            ;;
        *)
            warn "Automatic Ollama installation not supported on $PLATFORM"
            return
            ;;
    esac

    success "Ollama installed"

    # Start Ollama in the background
    info "Starting Ollama service..."
    if [[ "$PLATFORM" == "macos" ]]; then
        # On macOS, brew services or launch in background
        if command -v brew >/dev/null 2>&1; then
            brew services start ollama 2>/dev/null || ollama serve > /dev/null 2>&1 &
        else
            ollama serve > /dev/null 2>&1 &
        fi
    else
        # On Linux, start as background process
        ollama serve > /dev/null 2>&1 &
    fi

    # Wait a moment for Ollama to start
    sleep 2

    # Read default model from defaults.yml
    local default_model="llama3.2:1b"  # Fallback
    if [[ -f "$VECTROLA_INSTALL_DIR/vectrola/defaults.yml" ]]; then
        default_model=$(grep "default_model:" "$VECTROLA_INSTALL_DIR/vectrola/defaults.yml" | awk '{print $2}' | tr -d '"')
    fi

    # Pull the default model
    info "Downloading LLM model ($default_model)..."
    echo "   ${DIM}This may take a few minutes on first run...${RESET}"
    if ollama pull "$default_model"; then
        success "LLM model ready"
    else
        warn "Failed to download model - you can run 'ollama pull $default_model' later"
    fi
}

verify_installation() {
    step "Verifying installation..."

    # Activate venv
    # shellcheck source=/dev/null
    source "$VECTROLA_INSTALL_DIR/.venv/bin/activate"

    if vectrola --version >/dev/null 2>&1; then
        success "Vectrola CLI working"
    else
        warn "Vectrola CLI check had issues"
    fi
}

print_next_steps() {
    echo ""
    print_separator
    echo ""
    echo "${GREEN}${BOLD}✓ Installation complete!${RESET}"
    echo ""
    echo "${BOLD}Next steps:${RESET}"
    echo ""
    echo "  1. Reload your shell:"
    local shell_name
    shell_name=$(basename "${SHELL:-/bin/bash}")
    case "$shell_name" in
        zsh)  echo "     ${CYAN}source ~/.zshrc${RESET}" ;;
        bash)
            if [[ "$PLATFORM" == "macos" ]]; then
                echo "     ${CYAN}source ~/.bash_profile${RESET}"
            else
                echo "     ${CYAN}source ~/.bashrc${RESET}"
            fi
            ;;
        fish) echo "     ${CYAN}source ~/.config/fish/config.fish${RESET}" ;;
        *)    echo "     ${CYAN}exec \$SHELL${RESET}" ;;
    esac
    echo ""

    if [[ "$LLM_TYPE" == "local" && "${INSTALL_OLLAMA:-false}" == "true" ]]; then
        echo "  ${GREEN}✓${RESET} Ollama installed and model downloaded"
        echo ""
    elif [[ "$LLM_TYPE" == "local" && "$OLLAMA_AVAILABLE" != "true" ]]; then
        echo "  2. Install Ollama (required for semantic analysis):"
        case "$PLATFORM" in
            macos)
                echo "     ${CYAN}brew install ollama${RESET}"
                echo "     Or download from: https://ollama.ai/download"
                ;;
            linux)
                echo "     ${CYAN}curl -fsSL https://ollama.ai/install.sh | sh${RESET}"
                ;;
        esac
        echo ""
        echo "  3. Start Ollama and pull a model:"
        echo "     ${CYAN}ollama serve${RESET}          # In one terminal"
        echo "     ${CYAN}ollama pull llama3.2:1b${RESET}  # In another terminal"
        echo ""
    elif [[ "$LLM_TYPE" == "local" && "$OLLAMA_RUNNING" != "true" ]]; then
        echo "  2. Start Ollama:"
        echo "     ${CYAN}ollama serve${RESET}"
        echo "     ${CYAN}ollama pull llama3.2:1b${RESET}  # If you haven't already"
        echo ""
    fi

    echo "  Then try:"
    echo "     ${CYAN}vectrola status${RESET}              # Check system status"
    echo "     ${CYAN}vectrola ingest /path/to/music${RESET}  # Ingest your music"
    echo "     ${CYAN}vectrola search \"sad song\"${RESET}     # Search by mood"
    echo ""
    echo "Documentation: ${CYAN}https://github.com/Arunes007/vectrola#readme${RESET}"
    echo ""
}

# ============================================================================
# Help and Arguments
# ============================================================================

show_help() {
    cat << EOF
Vectrola Installer

USAGE:
    curl -fsSL https://raw.githubusercontent.com/Arunes007/vectrola/main/installer/install.sh | bash
    curl ... | bash -s -- [OPTIONS]

OPTIONS:
    -h, --help              Show this help message
    --non-interactive       Skip prompts, use defaults or specified options
    --llm=TYPE              LLM type: local (default), remote
    --llm-url=URL           Custom LLM URL (implies --llm=remote)
    --qdrant=TYPE           Qdrant type: hosted (default), local, remote
    --qdrant-url=URL        Custom Qdrant URL (implies --qdrant=remote)
    --qdrant-api-key=KEY    Qdrant API key (for authenticated remotes)

ENVIRONMENT VARIABLES:
    VECTROLA_VERSION        Git branch/tag to install (default: main)
    VECTROLA_INSTALL_DIR    Installation directory (default: ~/.vectrola)
    VECTROLA_CONFIG_DIR     Config directory (default: ~/.config/vectrola)

FEATURES:
    • Interactive mode asks to install Ollama if you choose Local LLM
    • Non-interactive mode auto-installs Ollama for Local LLM (if missing)
    • Automatically downloads the default LLM model from vectrola/defaults.yml

EXAMPLES:
    # Interactive installation (recommended)
    curl -fsSL .../install.sh | bash

    # Non-interactive with defaults (local Ollama + hosted Qdrant)
    # Will auto-install Ollama if missing
    curl ... | bash -s -- --non-interactive

    # Non-interactive with local everything
    curl ... | bash -s -- --non-interactive --llm=local --qdrant=local

    # Non-interactive with custom remote Qdrant
    curl ... | bash -s -- --non-interactive --qdrant-url=https://my-qdrant.example.com
EOF
}

parse_args() {
    NON_INTERACTIVE=false
    LLM_TYPE=""
    QDRANT_TYPE=""
    OLLAMA_HOST=""
    QDRANT_URL=""
    QDRANT_API_KEY=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)
                show_help
                exit 0
                ;;
            --non-interactive)
                NON_INTERACTIVE=true
                ;;
            --llm=*)
                LLM_TYPE="${1#*=}"
                ;;
            --llm-url=*)
                LLM_TYPE="remote"
                OLLAMA_HOST="${1#*=}"
                ;;
            --qdrant=*)
                QDRANT_TYPE="${1#*=}"
                ;;
            --qdrant-url=*)
                QDRANT_TYPE="remote"
                QDRANT_URL="${1#*=}"
                ;;
            --qdrant-api-key=*)
                QDRANT_API_KEY="${1#*=}"
                ;;
            *)
                error "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
        shift
    done

    # Set defaults for non-interactive mode
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        LLM_TYPE="${LLM_TYPE:-local}"
        QDRANT_TYPE="${QDRANT_TYPE:-hosted}"

        case "$LLM_TYPE" in
            local)
                OLLAMA_HOST="${OLLAMA_HOST:-$DEFAULT_OLLAMA_HOST}"
                # Auto-install Ollama in non-interactive mode if not present
                if [[ "$OLLAMA_AVAILABLE" != "true" ]]; then
                    INSTALL_OLLAMA=true
                fi
                ;;
            remote)
                if [[ -z "$OLLAMA_HOST" ]]; then
                    error "--llm-url is required when using --llm=remote"
                    exit 1
                fi
                ;;
            *)
                error "Invalid --llm type: $LLM_TYPE (use: local, remote)"
                exit 1
                ;;
        esac

        case "$QDRANT_TYPE" in
            hosted) QDRANT_URL="${QDRANT_URL:-$DEFAULT_QDRANT_HOSTED}" ;;
            local)  QDRANT_URL="${QDRANT_URL:-$DEFAULT_QDRANT_LOCAL}" ;;
            remote)
                if [[ -z "$QDRANT_URL" ]]; then
                    error "--qdrant-url is required when using --qdrant=remote"
                    exit 1
                fi
                ;;
            *)
                error "Invalid --qdrant type: $QDRANT_TYPE (use: hosted, local, remote)"
                exit 1
                ;;
        esac
    fi
}

# ============================================================================
# Main
# ============================================================================

main() {
    setup_colors
    parse_args "$@"
    print_header

    echo "${BOLD}Checking prerequisites...${RESET}"
    echo ""

    detect_platform
    check_git
    check_python
    check_ollama
    check_docker

    # Interactive configuration
    if [[ "$NON_INTERACTIVE" != "true" ]]; then
        prompt_llm_config
        prompt_qdrant_config
        confirm_config
    else
        echo ""
        info "Non-interactive mode: using LLM=$LLM_TYPE, Qdrant=$QDRANT_TYPE"
    fi

    echo ""
    print_separator
    echo ""
    echo "${BOLD}Installing Vectrola...${RESET}"
    echo ""

    clone_repo
    setup_venv
    install_deps
    write_config
    configure_shell
    install_ollama
    setup_local_qdrant
    verify_installation

    print_next_steps
}

main "$@"
