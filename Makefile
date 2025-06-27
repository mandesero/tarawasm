.PHONY: install system-check sdk-check check build shellcheck

SHELLCHECK_FILES := $(shell git ls-files '*.sh')

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
