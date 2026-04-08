PLANTUML_DIR = docs/plantuml
PLANTUML_OUT = docs/images
PLANTUML_SRC = $(wildcard $(PLANTUML_DIR)/*.puml)
PLANTUML_PNG = $(patsubst $(PLANTUML_DIR)/%.puml,$(PLANTUML_OUT)/%.png,$(PLANTUML_SRC))

.PHONY: docs clean-docs install test lint

docs: $(PLANTUML_PNG)
	@echo "PlantUML diagrams compiled to $(PLANTUML_OUT)/"

$(PLANTUML_OUT)/%.png: $(PLANTUML_DIR)/%.puml
	@mkdir -p $(PLANTUML_OUT)
	plantuml -tpng -o $(CURDIR)/$(PLANTUML_OUT) $<

install:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

test:
	.venv/bin/pytest -v

lint:
	.venv/bin/ruff check src/ tests/
	.venv/bin/ruff format --check src/ tests/

clean-docs:
	rm -rf $(PLANTUML_OUT)
