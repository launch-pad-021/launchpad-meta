.PHONY: bootstrap bootstrap-install preflight preflight-a0 validate test test-agent-kit

bootstrap:
	scripts/bootstrap-local.sh

bootstrap-install:
	scripts/bootstrap-local.sh --install

preflight:
	scripts/preflight.sh --phase step-minus-one

preflight-a0:
	scripts/preflight.sh --phase a0

validate:
	scripts/validate-spec-pack.sh

test:
	python3 -m unittest discover -s tests -v

test-agent-kit:
	@test -d ../launchpad-agent-kit || { echo "Missing sibling repository: ../launchpad-agent-kit" >&2; exit 1; }
	uv run --with pytest pytest -q ../launchpad-agent-kit/scripts/test_risk.py
