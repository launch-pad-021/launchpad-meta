.PHONY: bootstrap bootstrap-install preflight preflight-a0 preflight-strict validate test test-agent-kit test-control-plane

bootstrap:
	scripts/bootstrap-local.sh

bootstrap-install:
	scripts/bootstrap-local.sh --install

preflight:
	scripts/preflight.sh --phase step-minus-one

preflight-a0:
	scripts/preflight.sh --phase a0

preflight-strict:
	scripts/preflight.sh --phase step-minus-one --strict

validate:
	scripts/validate-spec-pack.sh

test:
	python3 -m unittest discover -s tests -v

test-control-plane:
	python3 -m unittest tests.test_agent_control tests.test_control_tools tests.test_control_workflows -v

test-agent-kit:
	scripts/preflight.sh --test-agent-kit
