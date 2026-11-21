.PHONY: bootstrap bootstrap-install preflight preflight-a0 preflight-strict validate test test-agent-kit test-control-plane test-repo-provisioning test-a0-drills evidence-a0

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

test-repo-provisioning:
	python3 -m unittest tests.test_create_repos -v
	bash -n scripts/create-repos.sh

test-a0-drills:
	python3 -m unittest tests.test_a0_drills -v
	python3 scripts/a0_drills.py >/dev/null

evidence-a0:
	python3 scripts/a0_drills.py --write docs/verification/A0 >/dev/null
