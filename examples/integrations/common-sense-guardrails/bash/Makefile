SCENARIO ?= car-wash
MODE ?= mock
STAGE ?= ce

.PHONY: run test clean

run:
	bash main.sh --scenario "$(SCENARIO)" --mode "$(MODE)" --stage "$(STAGE)"

test:
	bash test.sh

clean:
	rm -rf .tmp
