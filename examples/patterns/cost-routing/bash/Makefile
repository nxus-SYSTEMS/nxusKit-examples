SCRIPT       = main.sh
EXAMPLE_NAME = cost-routing
ARGS         ?=

.PHONY: build run test clean

build:
	@bash -n $(SCRIPT) && echo "$(EXAMPLE_NAME): syntax OK"

run: build
	@bash $(SCRIPT) $(ARGS)

test: build
	@echo "$(EXAMPLE_NAME): running structural tests..."
	@bash $(SCRIPT) 2>&1 | grep -qE "economy|standard|premium" && echo "  tier classification: PASS"
	@echo "$(EXAMPLE_NAME): all tests PASS"

clean:
	@rm -rf .tmp/
	@echo "$(EXAMPLE_NAME): cleaned"
