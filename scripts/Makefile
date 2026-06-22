.PHONY: install grammars test lint clean build-all

# ── 安装 ─────────────────────────────────────────────────────────────
install:
	pip install -e ".[dev]"

# ── Grammar 编译 ──────────────────────────────────────────────────────
# 编译 tree-sitter grammar 到共享库 (.so / .dylib)
grammars:
	python code_index/grammars/build.py

grammars-kotlin:
	python code_index/grammars/build.py --lang kotlin

grammars-java:
	python code_index/grammars/build.py --lang java

grammars-swift:
	python code_index/grammars/build.py --lang swift

grammars-typescript:
	python code_index/grammars/build.py --lang typescript

# ── 测试 ─────────────────────────────────────────────────────────────
test:
	pytest tests/ -v

test-cov:
	pytest tests/ --cov=code_index --cov-report=term-missing -v

# ── Lint ─────────────────────────────────────────────────────────────
lint:
	python -m py_compile code_index/**/*.py cli.py
	@echo "Syntax check passed."

# ── 清理 ─────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache dist build *.egg-info

# ── 全量构建（供 CI 使用）───────────────────────────────────────────
build-all: install grammars
	@echo "Build complete."

# ── 帮助 ─────────────────────────────────────────────────────────────
help:
	@echo "Available targets:"
	@echo "  install      - pip install -e .[dev]"
	@echo "  grammars     - compile all tree-sitter grammars"
	@echo "  test         - run pytest"
	@echo "  test-cov     - run pytest with coverage"
	@echo "  lint         - syntax check"
	@echo "  clean        - remove build artifacts"
	@echo "  build-all    - install + grammars"
