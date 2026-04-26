PLANTUML_DIR = docs/plantuml
PLANTUML_OUT = docs/images
PLANTUML_SRC = $(wildcard $(PLANTUML_DIR)/*.puml)
PLANTUML_PNG = $(patsubst $(PLANTUML_DIR)/%.puml,$(PLANTUML_OUT)/%.png,$(PLANTUML_SRC))

.PHONY: docs clean-docs install install-topics test lint

docs: $(PLANTUML_PNG)
	@echo "PlantUML diagrams compiled to $(PLANTUML_OUT)/"

$(PLANTUML_OUT)/%.png: $(PLANTUML_DIR)/%.puml
	@mkdir -p $(PLANTUML_OUT)
	plantuml -tpng -o $(CURDIR)/$(PLANTUML_OUT) $<

install:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

# Install ML/topics dependencies.
# On macOS with Python 3.14+ (Homebrew), pip may fail with a libexpat symbol
# error because the system libexpat is older than the one Python was compiled
# against.  Setting DYLD_LIBRARY_PATH to Homebrew's expat library fixes it.
# Adjust the expat version in the path if needed (brew info expat).
install-topics:
	@echo "Installing topic-modeling dependencies..."
	@if [ "$$(uname)" = "Darwin" ]; then \
		EXPAT_LIB=$$(brew --prefix expat 2>/dev/null)/lib; \
		if [ -d "$$EXPAT_LIB" ]; then \
			echo "macOS detected: using DYLD_LIBRARY_PATH=$$EXPAT_LIB"; \
			DYLD_LIBRARY_PATH=$$EXPAT_LIB .venv/bin/pip install -e ".[topics]"; \
		else \
			.venv/bin/pip install -e ".[topics]"; \
		fi; \
	else \
		.venv/bin/pip install -e ".[topics]"; \
	fi
	@echo "Done. Run 'wst topics build' to generate your topic vocabulary."

test:
	.venv/bin/pytest -v

lint:
	.venv/bin/ruff check src/ tests/
	.venv/bin/ruff format --check src/ tests/

clean-docs:
	rm -rf $(PLANTUML_OUT)
