#Requires -Version 5.1
<#
.SYNOPSIS
    Vectrola Installer for Windows

.DESCRIPTION
    Installs Vectrola - Multimodal Music Knowledge Graph
    Interactive setup with LLM and Vector Database configuration.

.EXAMPLE
    irm https://raw.githubusercontent.com/Arunes007/vectrola/main/installer/install.ps1 | iex

.EXAMPLE
    # Non-interactive with defaults
    & ([scriptblock]::Create((irm .../install.ps1))) -NonInteractive

.EXAMPLE
    # Non-interactive with local Qdrant
    & ([scriptblock]::Create((irm .../install.ps1))) -NonInteractive -Qdrant local
#>

[CmdletBinding()]
param(
    [switch]$NonInteractive,
    [ValidateSet('local', 'remote')]
    [string]$Llm = '',
    [string]$LlmUrl = '',
    [ValidateSet('hosted', 'local', 'remote')]
    [string]$Qdrant = '',
    [string]$QdrantUrl = '',
    [string]$QdrantApiKey = '',
    [switch]$Help
)

$ErrorActionPreference = 'Stop'

# ============================================================================
# Configuration
# ============================================================================

$VectrolaVersion = $env:VECTROLA_VERSION ?? 'main'
$VectrolaRepo = 'https://github.com/Arunes007/vectrola'
$VectrolaInstallDir = $env:VECTROLA_INSTALL_DIR ?? "$env:USERPROFILE\.vectrola"
$VectrolaConfigDir = $env:VECTROLA_CONFIG_DIR ?? "$env:USERPROFILE\.config\vectrola"

$DefaultOllamaHost = 'http://localhost:11434'
$DefaultQdrantHosted = 'https://qdrant.vectrola.dev'
$DefaultQdrantLocal = 'http://localhost:6333'

# ============================================================================
# Output Functions
# ============================================================================

function Write-Info { Write-Host "i " -ForegroundColor Cyan -NoNewline; Write-Host $args }
function Write-Success { Write-Host "✓ " -ForegroundColor Green -NoNewline; Write-Host $args }
function Write-Warn { Write-Host "⚠ " -ForegroundColor Yellow -NoNewline; Write-Host $args }
function Write-Err { Write-Host "✗ " -ForegroundColor Red -NoNewline; Write-Host $args }
function Write-Step { Write-Host "→ " -ForegroundColor Magenta -NoNewline; Write-Host $args }

function Write-Header {
    Write-Host ""
    Write-Host "🎧 Vectrola Installer" -ForegroundColor White
    Write-Host "   Multimodal Music Knowledge Graph" -ForegroundColor DarkGray
    Write-Host ""
}

function Write-Separator {
    Write-Host ("━" * 56) -ForegroundColor DarkGray
}

function Show-Help {
    @"
Vectrola Installer for Windows

USAGE:
    irm https://raw.githubusercontent.com/Arunes007/vectrola/main/installer/install.ps1 | iex

OPTIONS:
    -Help               Show this help message
    -NonInteractive     Skip prompts, use defaults or specified options
    -Llm TYPE           LLM type: local (default), remote
    -LlmUrl URL         Custom LLM URL (implies -Llm remote)
    -Qdrant TYPE        Qdrant type: hosted (default), local, remote
    -QdrantUrl URL      Custom Qdrant URL (implies -Qdrant remote)
    -QdrantApiKey KEY   Qdrant API key (for authenticated remotes)

ENVIRONMENT VARIABLES:
    VECTROLA_VERSION        Git branch/tag to install (default: main)
    VECTROLA_INSTALL_DIR    Installation directory (default: ~/.vectrola)
    VECTROLA_CONFIG_DIR     Config directory (default: ~/.config/vectrola)

EXAMPLES:
    # Interactive installation (recommended)
    irm .../install.ps1 | iex

    # Non-interactive with defaults
    & ([scriptblock]::Create((irm .../install.ps1))) -NonInteractive

    # Non-interactive with local Qdrant
    & ([scriptblock]::Create((irm .../install.ps1))) -NonInteractive -Qdrant local
"@
}

# ============================================================================
# Prerequisite Checks
# ============================================================================

function Test-Git {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Err "Git is required but not installed"
        Write-Host ""
        Write-Host "  Install with: " -NoNewline
        Write-Host "winget install Git.Git" -ForegroundColor Cyan
        Write-Host "  Or download:  https://git-scm.com/download/win"
        exit 1
    }

    $version = (git --version) -replace 'git version ', ''
    Write-Success "Git $version found"
}

function Test-Python {
    $minVersion = [version]'3.10'

    foreach ($cmd in @('python', 'python3', 'py')) {
        try {
            $versionStr = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($versionStr) {
                $version = [version]$versionStr
                if ($version -ge $minVersion) {
                    $script:PythonCmd = $cmd
                    $script:PythonVersion = $versionStr
                    Write-Success "Python $versionStr found"
                    return
                }
            }
        } catch {}
    }

    Write-Err "Python 3.10+ is required"
    Write-Host ""
    Write-Host "  Install with: " -NoNewline
    Write-Host "winget install Python.Python.3.11" -ForegroundColor Cyan
    Write-Host "  Or download:  https://www.python.org/downloads/"
    exit 1
}

function Test-Ollama {
    if (Get-Command ollama -ErrorAction SilentlyContinue) {
        try {
            $null = Invoke-WebRequest -Uri "$DefaultOllamaHost/api/tags" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
            Write-Success "Ollama is installed and running"
            $script:OllamaAvailable = $true
            $script:OllamaRunning = $true
        } catch {
            Write-Warn "Ollama is installed but not running"
            $script:OllamaAvailable = $true
            $script:OllamaRunning = $false
        }
    } else {
        Write-Info "Ollama not found (needed for local LLM)"
        $script:OllamaAvailable = $false
        $script:OllamaRunning = $false
    }
}

function Test-Docker {
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        try {
            $null = docker info 2>$null
            $containers = docker ps --format '{{.Names}}' 2>$null
            if ($containers -match '^qdrant$') {
                Write-Success "Docker available, Qdrant container running"
                $script:DockerAvailable = $true
                $script:QdrantRunning = $true
            } else {
                Write-Success "Docker available"
                $script:DockerAvailable = $true
                $script:QdrantRunning = $false
            }
        } catch {
            Write-Info "Docker installed but daemon not running"
            $script:DockerAvailable = $false
            $script:QdrantRunning = $false
        }
    } else {
        Write-Info "Docker not found (needed for local Qdrant)"
        $script:DockerAvailable = $false
        $script:QdrantRunning = $false
    }
}

# ============================================================================
# Interactive Configuration
# ============================================================================

function Get-LlmConfig {
    Write-Host ""
    Write-Separator
    Write-Host "                    CONFIGURATION" -ForegroundColor White
    Write-Separator
    Write-Host ""

    Write-Host "1. LLM for Semantic Analysis" -ForegroundColor White
    Write-Host "   Vectrola uses an LLM to extract themes, moods, and narratives." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "   [" -NoNewline; Write-Host "1" -ForegroundColor Cyan -NoNewline; Write-Host "] Local Ollama " -NoNewline
    Write-Host "(recommended - private, no API costs)" -ForegroundColor DarkGray
    Write-Host "   [" -NoNewline; Write-Host "2" -ForegroundColor Cyan -NoNewline; Write-Host "] Remote LLM endpoint " -NoNewline
    Write-Host "(bring your own URL)" -ForegroundColor DarkGray
    Write-Host ""

    $choice = Read-Host "   Choice [1]"
    if ([string]::IsNullOrWhiteSpace($choice)) { $choice = '1' }

    switch ($choice) {
        '1' {
            $script:LlmType = 'local'
            $script:OllamaHost = $DefaultOllamaHost
        }
        '2' {
            $script:LlmType = 'remote'
            $script:OllamaHost = Read-Host "   Enter LLM endpoint URL"
            if ([string]::IsNullOrWhiteSpace($script:OllamaHost)) {
                Write-Err "URL cannot be empty"
                exit 1
            }
        }
        default {
            Write-Err "Invalid choice: $choice"
            exit 1
        }
    }
}

function Get-QdrantConfig {
    Write-Host ""
    Write-Host "2. Vector Database " -ForegroundColor White -NoNewline
    Write-Host "(for semantic search)" -ForegroundColor DarkGray
    Write-Host "   Store and search music embeddings." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "   [" -NoNewline; Write-Host "1" -ForegroundColor Cyan -NoNewline; Write-Host "] Hosted Qdrant " -NoNewline
    Write-Host "(easy start - no Docker needed)" -ForegroundColor DarkGray
    Write-Host "   [" -NoNewline; Write-Host "2" -ForegroundColor Cyan -NoNewline; Write-Host "] Local Qdrant via Docker"
    Write-Host "   [" -NoNewline; Write-Host "3" -ForegroundColor Cyan -NoNewline; Write-Host "] Remote Qdrant " -NoNewline
    Write-Host "(bring your own URL)" -ForegroundColor DarkGray
    Write-Host ""

    $choice = Read-Host "   Choice [1]"
    if ([string]::IsNullOrWhiteSpace($choice)) { $choice = '1' }

    switch ($choice) {
        '1' {
            $script:QdrantType = 'hosted'
            $script:QdrantUrlValue = $DefaultQdrantHosted
        }
        '2' {
            $script:QdrantType = 'local'
            $script:QdrantUrlValue = $DefaultQdrantLocal
        }
        '3' {
            $script:QdrantType = 'remote'
            $script:QdrantUrlValue = Read-Host "   Enter Qdrant URL"
            if ([string]::IsNullOrWhiteSpace($script:QdrantUrlValue)) {
                Write-Err "URL cannot be empty"
                exit 1
            }
            $script:QdrantApiKeyValue = Read-Host "   Enter Qdrant API key (or press Enter to skip)"
        }
        default {
            Write-Err "Invalid choice: $choice"
            exit 1
        }
    }
}

function Confirm-Config {
    Write-Host ""
    Write-Separator
    Write-Host ""
    Write-Host "Installing with configuration:" -ForegroundColor White
    Write-Host ""

    if ($script:LlmType -eq 'local') {
        Write-Host "  • LLM: " -NoNewline; Write-Host "Local Ollama" -ForegroundColor Cyan -NoNewline
        Write-Host " ($script:OllamaHost)"
    } else {
        Write-Host "  • LLM: " -NoNewline; Write-Host "Remote" -ForegroundColor Cyan -NoNewline
        Write-Host " ($script:OllamaHost)"
    }

    switch ($script:QdrantType) {
        'hosted' {
            Write-Host "  • Qdrant: " -NoNewline; Write-Host "Hosted" -ForegroundColor Cyan -NoNewline
            Write-Host " ($script:QdrantUrlValue)"
        }
        'local' {
            Write-Host "  • Qdrant: " -NoNewline; Write-Host "Local Docker" -ForegroundColor Cyan -NoNewline
            Write-Host " ($script:QdrantUrlValue)"
        }
        'remote' {
            Write-Host "  • Qdrant: " -NoNewline; Write-Host "Remote" -ForegroundColor Cyan -NoNewline
            Write-Host " ($script:QdrantUrlValue)"
        }
    }

    Write-Host ""

    $confirm = Read-Host "Proceed? [Y/n]"
    if ([string]::IsNullOrWhiteSpace($confirm)) { $confirm = 'Y' }

    if ($confirm -notmatch '^[Yy]$') {
        Write-Host "Installation cancelled."
        exit 0
    }
}

# ============================================================================
# Installation Functions
# ============================================================================

function Install-Repository {
    Write-Step "Cloning Vectrola..."

    if (Test-Path $VectrolaInstallDir) {
        Write-Info "Existing installation found, updating..."
        Push-Location $VectrolaInstallDir
        try {
            git fetch origin $VectrolaVersion --depth 1 2>$null
            git reset --hard "origin/$VectrolaVersion" 2>$null
        } catch {
            git reset --hard $VectrolaVersion
        }
        Pop-Location
    } else {
        git clone --depth 1 --branch $VectrolaVersion $VectrolaRepo $VectrolaInstallDir
    }

    Write-Success "Source code ready at $VectrolaInstallDir"
}

function Install-Venv {
    Write-Step "Setting up Python environment..."

    $venvDir = "$VectrolaInstallDir\.venv"

    if (Test-Path $venvDir) {
        # Check if existing venv is compatible
        try {
            $venvPython = & "$venvDir\Scripts\python.exe" -c "import sys; print(sys.version_info >= (3,10))" 2>$null
            if ($venvPython -ne 'True') {
                Write-Warn "Existing venv has incompatible Python, recreating..."
                Remove-Item -Recurse -Force $venvDir
            }
        } catch {
            Remove-Item -Recurse -Force $venvDir
        }
    }

    if (-not (Test-Path $venvDir)) {
        & $PythonCmd -m venv $venvDir
    }

    Write-Success "Virtual environment ready"
}

function Install-Dependencies {
    Write-Step "Installing dependencies..."

    $venvPip = "$VectrolaInstallDir\.venv\Scripts\pip.exe"

    & $venvPip install --upgrade pip --quiet
    Push-Location $VectrolaInstallDir
    & $venvPip install -e ".[full]" --quiet
    Pop-Location

    Write-Success "Dependencies installed"
}

function Write-Config {
    Write-Step "Writing configuration..."

    if (-not (Test-Path $VectrolaConfigDir)) {
        New-Item -ItemType Directory -Path $VectrolaConfigDir -Force | Out-Null
    }

    $envFile = "$VectrolaConfigDir\.env"
    $date = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

    $content = @"
# Generated by Vectrola installer on $date
# Edit this file to change your configuration

# LLM Configuration
OLLAMA_HOST=$script:OllamaHost

# Vector Database Configuration
QDRANT_URL=$script:QdrantUrlValue
"@

    if (-not [string]::IsNullOrWhiteSpace($script:QdrantApiKeyValue)) {
        $content += "`nQDRANT_API_KEY=$script:QdrantApiKeyValue"
    }

    Set-Content -Path $envFile -Value $content

    Write-Success "Configuration saved to $envFile"
}

function Set-Path {
    Write-Step "Configuring PATH..."

    $venvBin = "$VectrolaInstallDir\.venv\Scripts"
    $currentPath = [Environment]::GetEnvironmentVariable('Path', 'User')

    if ($currentPath -notlike "*$venvBin*") {
        [Environment]::SetEnvironmentVariable('Path', "$venvBin;$currentPath", 'User')
        $env:Path = "$venvBin;$env:Path"
        Write-Success "Added Vectrola to PATH"
    } else {
        Write-Info "PATH already configured"
    }
}

function Install-LocalQdrant {
    if ($script:QdrantType -ne 'local') {
        return
    }

    Write-Step "Setting up local Qdrant..."

    if (-not $script:DockerAvailable) {
        Write-Warn "Docker not available - cannot start local Qdrant"
        Write-Host ""
        Write-Host "  Install Docker Desktop from: " -NoNewline
        Write-Host "https://docker.com/get-docker" -ForegroundColor Cyan
        Write-Host "  Then run: " -NoNewline
        Write-Host "docker run -d --name qdrant -p 6333:6333 qdrant/qdrant" -ForegroundColor Cyan
        return
    }

    if ($script:QdrantRunning) {
        Write-Success "Qdrant container already running"
        return
    }

    $containers = docker ps -a --format '{{.Names}}' 2>$null
    if ($containers -match '^qdrant$') {
        Write-Info "Starting existing Qdrant container..."
        docker start qdrant
    } else {
        Write-Info "Creating Qdrant container..."
        docker run -d `
            --name qdrant `
            -p 6333:6333 `
            -v "$VectrolaConfigDir\qdrant:/qdrant/storage" `
            qdrant/qdrant
    }

    Write-Success "Qdrant container started"
}

function Test-Installation {
    Write-Step "Verifying installation..."

    $vectrola = "$VectrolaInstallDir\.venv\Scripts\vectrola.exe"

    if (Test-Path $vectrola) {
        try {
            & $vectrola --version | Out-Null
            Write-Success "Vectrola CLI working"
        } catch {
            Write-Warn "Vectrola CLI check had issues"
        }
    } else {
        Write-Warn "Vectrola executable not found"
    }
}

function Write-NextSteps {
    Write-Host ""
    Write-Separator
    Write-Host ""
    Write-Host "✓ Installation complete!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor White
    Write-Host ""
    Write-Host "  1. Open a new terminal " -NoNewline
    Write-Host "(to pick up PATH changes)" -ForegroundColor DarkGray
    Write-Host ""

    if ($script:LlmType -eq 'local' -and -not $script:OllamaAvailable) {
        Write-Host "  2. Install Ollama (required for semantic analysis):"
        Write-Host "     Download from: " -NoNewline
        Write-Host "https://ollama.ai/download" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  3. Start Ollama and pull a model:"
        Write-Host "     " -NoNewline; Write-Host "ollama serve" -ForegroundColor Cyan
        Write-Host "     " -NoNewline; Write-Host "ollama pull qwen2.5:3b" -ForegroundColor Cyan
        Write-Host ""
    } elseif ($script:LlmType -eq 'local' -and -not $script:OllamaRunning) {
        Write-Host "  2. Start Ollama:"
        Write-Host "     " -NoNewline; Write-Host "ollama serve" -ForegroundColor Cyan
        Write-Host "     " -NoNewline; Write-Host "ollama pull qwen2.5:3b" -ForegroundColor Cyan -NoNewline
        Write-Host "  # If you haven't already" -ForegroundColor DarkGray
        Write-Host ""
    }

    Write-Host "  Then try:"
    Write-Host "     " -NoNewline; Write-Host "vectrola status" -ForegroundColor Cyan -NoNewline
    Write-Host "              # Check system status" -ForegroundColor DarkGray
    Write-Host "     " -NoNewline; Write-Host "vectrola ingest C:\Music" -ForegroundColor Cyan -NoNewline
    Write-Host "     # Ingest your music" -ForegroundColor DarkGray
    Write-Host "     " -NoNewline; Write-Host 'vectrola search "sad song"' -ForegroundColor Cyan -NoNewline
    Write-Host "    # Search by mood" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "Documentation: " -NoNewline
    Write-Host "https://github.com/Arunes007/vectrola#readme" -ForegroundColor Cyan
    Write-Host ""
}

# ============================================================================
# Main
# ============================================================================

if ($Help) {
    Show-Help
    exit 0
}

Write-Header

Write-Host "Checking prerequisites..." -ForegroundColor White
Write-Host ""

Test-Git
Test-Python
Test-Ollama
Test-Docker

# Handle arguments for non-interactive mode
if ($NonInteractive) {
    # Set defaults
    $script:LlmType = if ($Llm) { $Llm } else { 'local' }
    $script:QdrantType = if ($Qdrant) { $Qdrant } else { 'hosted' }

    # Set URLs based on type
    switch ($script:LlmType) {
        'local' { $script:OllamaHost = if ($LlmUrl) { $LlmUrl } else { $DefaultOllamaHost } }
        'remote' {
            if ([string]::IsNullOrWhiteSpace($LlmUrl)) {
                Write-Err "-LlmUrl is required when using -Llm remote"
                exit 1
            }
            $script:OllamaHost = $LlmUrl
        }
    }

    switch ($script:QdrantType) {
        'hosted' { $script:QdrantUrlValue = if ($QdrantUrl) { $QdrantUrl } else { $DefaultQdrantHosted } }
        'local' { $script:QdrantUrlValue = if ($QdrantUrl) { $QdrantUrl } else { $DefaultQdrantLocal } }
        'remote' {
            if ([string]::IsNullOrWhiteSpace($QdrantUrl)) {
                Write-Err "-QdrantUrl is required when using -Qdrant remote"
                exit 1
            }
            $script:QdrantUrlValue = $QdrantUrl
        }
    }

    $script:QdrantApiKeyValue = $QdrantApiKey

    Write-Host ""
    Write-Info "Non-interactive mode: using LLM=$script:LlmType, Qdrant=$script:QdrantType"
} else {
    Get-LlmConfig
    Get-QdrantConfig
    Confirm-Config
}

Write-Host ""
Write-Separator
Write-Host ""
Write-Host "Installing Vectrola..." -ForegroundColor White
Write-Host ""

Install-Repository
Install-Venv
Install-Dependencies
Write-Config
Set-Path
Install-LocalQdrant
Test-Installation

Write-NextSteps
