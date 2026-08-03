.PHONY: install system-check sdk-check check build shellcheck test-docker-amd64 test-upstream-amd64

SHELLCHECK_FILES = $(shell find docker-scripts scripts -type f -name '*.sh' -print | sort)

install:
	@./scripts/install_deps.sh

system-check:
	@echo "==> Verifying system toolchain…"
	@./scripts/verify-system.sh

sdk-check:
	@echo "==> Verifying SDK and Python deps…"
	@./scripts/verify-sdk.sh

check: system-check sdk-check
	@echo "All checks passed!"

build:
	@./scripts/build.sh

shellcheck:
	@shellcheck $(SHELLCHECK_FILES)

test-docker-amd64:
	@echo "==> Building test image for linux/amd64..."
	@docker buildx build --platform linux/amd64 --load -t tarawasm:test-amd64 .
	@echo "==> Running docker-mode pytest on linux/amd64..."
	@TARAWASM_DOCKER_IMAGE=tarawasm:test-amd64 TARAWASM_DOCKER_PLATFORM=linux/amd64 TARAWASM_RUNTIME_MODE=docker WASM_RUNTIME=wasmtime PYTHONPATH=. python3 -m pytest -k "cli:docker" -vv

test-upstream-amd64:
	@echo "==> Building test image for linux/amd64..."
	@docker buildx build --platform linux/amd64 --load -t tarawasm:test-amd64 .
	@echo "==> Running upstream tool-repo integration tests..."
	@TARAWASM_DOCKER_IMAGE=tarawasm:test-amd64 TARAWASM_DOCKER_PLATFORM=linux/amd64 TARAWASM_RUNTIME_MODE=docker TARAWASM_UPSTREAM_MODE=docker TARAWASM_UPSTREAM_IT=1 PYTHONPATH=. python3 -m pytest tests/test_upstream_tool_repos.py -vv
