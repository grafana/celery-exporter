.PHONY: help clean test
.DEFAULT_GOAL := help

DOCKER_REPO="grafana/celery-exporter"
DOCKER_VERSION="latest"

define PRINT_HELP_PYSCRIPT
import re, sys

for line in sys.stdin:
	match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-20s %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT

test: build_dev ## Run tests and coverage
	docker run ${DOCKER_REPO}:dev \
		/bin/ash -c "coverage run -m pytest && coverage report"

build: ## Build Docker file
	export DOCKER_REPO
	export DOCKER_VERSION

	docker build \
		--build-arg DOCKER_REPO=${DOCKER_REPO} \
		--build-arg VERSION=${DOCKER_VERSION} \
		--build-arg VCS_REF=`git rev-parse --short HEAD` \
		--build-arg BUILD_DATE=`date -u +”%Y-%m-%dT%H:%M:%SZ”` \
		-f ./Dockerfile \
		-t ${DOCKER_REPO}:${DOCKER_VERSION} \
		.

build_dev: ## Build development Docker file
	docker build \
		-f ./Dockerfile \
		--target dev \
		-t ${DOCKER_REPO}:dev \
		.

sh: build_dev ## Shell into development container
	docker run -it ${DOCKER_REPO}:dev /bin/ash

run: build ## Run in docker container
	docker run -p 9540:9540 ${DOCKER_REPO}:${DOCKER_VERSION}

help: ## Print this help
	@python -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)
          
