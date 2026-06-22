#!/usr/bin/env bash
# =============================================================================
# code-index 一键安装脚本
# =============================================================================
# 用法：
#   bash skill/install.sh           # 安装 Python 依赖 + 编译 grammar
#   bash skill/install.sh --no-grammar  # 只安装 Python 依赖（跳过 grammar 编译）
#
# 前提：
#   - Python >= 3.10
#   - git
#   - pip
# =============================================================================

set -euo pipefail

# ── 颜色输出 ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()    { echo -e "${CYAN}[info]${NC}  $*"; }
success() { echo -e "${GREEN}[ok]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC}  $*"; }
error()   { echo -e "${RED}[error]${NC} $*" >&2; }

# ── 参数解析 ──────────────────────────────────────────────────────────────────
BUILD_GRAMMAR=true
for arg in "$@"; do
    case "$arg" in
        --no-grammar) BUILD_GRAMMAR=false ;;
        -h|--help)
            echo "Usage: bash scripts/install.sh [--no-grammar]"
            exit 0
            ;;
        *)
            error "Unknown argument: $arg"
            exit 1
            ;;
    esac
done

# ── 检查 Python 版本 ───────────────────────────────────────────────────────────
info "Checking Python version..."
PYTHON_CMD=""

# 候选命令：优先版本号明确的（3.13 → 3.12 → 3.11 → 3.10），再 fallback 到 python3 / python
# 同时也在常见的 Homebrew / pyenv / asdf 路径中查找
PYTHON_CANDIDATES=(
    python3.13 python3.12 python3.11 python3.10
    /opt/homebrew/bin/python3.13
    /opt/homebrew/bin/python3.12
    /opt/homebrew/bin/python3.11
    /opt/homebrew/bin/python3.10
    /usr/local/bin/python3.13
    /usr/local/bin/python3.12
    /usr/local/bin/python3.11
    /usr/local/bin/python3.10
    "$HOME/.pyenv/shims/python3"
    python3
    python
)

for cmd in "${PYTHON_CANDIDATES[@]}"; do
    if command -v "$cmd" &>/dev/null || [[ -x "$cmd" ]]; then
        version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null) || continue
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [[ $major -ge 3 && $minor -ge 10 ]]; then
            PYTHON_CMD="$cmd"
            success "Found Python $version at: $(command -v "$cmd" 2>/dev/null || echo "$cmd")"
            break
        else
            warn "$cmd version $version < 3.10, skipping"
        fi
    fi
done

if [[ -z "$PYTHON_CMD" ]]; then
    error "Python >= 3.10 is required but not found."
    error ""
    error "Searched candidates (none >= 3.10):"
    for cmd in python3.11 python3.10 python3 /opt/homebrew/bin/python3.11; do
        if command -v "$cmd" &>/dev/null || [[ -x "$cmd" ]]; then
            v=$("$cmd" --version 2>&1 || echo "unknown")
            error "  $cmd -> $v"
        fi
    done
    error ""
    error "Install options:"
    error "  Homebrew:  brew install python@3.11"
    error "  pyenv:     pyenv install 3.11 && pyenv global 3.11"
    exit 1
fi

# ── 检查 pip ──────────────────────────────────────────────────────────────────
info "Checking pip..."
if ! "$PYTHON_CMD" -m pip --version &>/dev/null; then
    error "pip not found. Please install pip and try again."
    exit 1
fi
success "pip found"

# ── 安装 Python 依赖 ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# pyproject.toml is co-located in the same scripts/ directory
REPO_ROOT="$SCRIPT_DIR"

info "Installing code-index package..."
cd "$REPO_ROOT"

# 优先使用 editable 安装（开发场景）
if [[ -f "pyproject.toml" ]]; then
    "$PYTHON_CMD" -m pip install -e ".[dev]" --quiet 2>/dev/null \
        || "$PYTHON_CMD" -m pip install -e . --quiet
    success "Installed code-index (editable mode)"
else
    error "pyproject.toml not found in $REPO_ROOT"
    exit 1
fi

# ── 验证 CLI 可用 ──────────────────────────────────────────────────────────────
info "Verifying CLI..."
if code-index --help &>/dev/null; then
    success "code-index CLI is available"
elif "$PYTHON_CMD" -m code_index.cli --help &>/dev/null; then
    warn "code-index CLI via 'python -m code_index.cli' (PATH may not include pip bin)"
    warn "Add pip bin to PATH: export PATH=\"\$PATH:\$($PYTHON_CMD -m site --user-base)/bin\""
else
    warn "CLI not immediately available, but package is installed."
fi

# ── 编译 Grammar（可选）──────────────────────────────────────────────────────
if [[ "$BUILD_GRAMMAR" == "true" ]]; then
    info "Building tree-sitter grammars (this may take a few minutes)..."
    if command -v git &>/dev/null; then
        if "$PYTHON_CMD" -m code_index.grammars.build kotlin java; then
            success "Grammars built successfully"
        else
            warn "Grammar build failed. You can retry manually:"
            warn "  python -m code_index.grammars.build"
        fi
    else
        warn "git not found — skipping grammar build."
        warn "Install git and run: python -m code_index.grammars.build"
    fi
else
    info "Skipping grammar build (--no-grammar)"
fi

# ── 完成提示 ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  code-index installed successfully!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo "Next steps:"
echo "  1. Build the index for your repo:"
echo "       code-index build"
echo ""
echo "  2. Search for a symbol:"
echo "       code-index query <SymbolName>"
echo ""
echo "  3. Check index status:"
echo "       code-index status"
echo ""
echo "  Run 'code-index --help' for full usage."
echo ""
