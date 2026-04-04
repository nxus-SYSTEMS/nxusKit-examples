SCRIPT       = main.sh
EXAMPLE_NAME = capability-detection
ARGS         ?=

.PHONY: build run test clean

build:
	@bash -n $(SCRIPT) && echo "$(EXAMPLE_NAME): syntax OK"

run: build
	@bash $(SCRIPT) $(ARGS)

test: build
	@echo "$(EXAMPLE_NAME): running structural tests..."
	@bash -c '\
		source ../../../shared/bash/nxuskit-common.sh && \
		parse_args && check_prereqs && \
		out=$$(tmpfile test-models.json) && \
		run_cli models -p ollama -f json -o "$$out" && \
		require_jq_key "$$out" ".result.models" && \
		echo "  models command: PASS" \
	'
	@echo "$(EXAMPLE_NAME): all tests PASS"

clean:
	@rm -rf .tmp/
	@echo "$(EXAMPLE_NAME): cleaned"
