.PHONY: help clean test
.DEFAULT_GOAL := help

DOCKER_REPO="grafana/celery-exporter"
DOCKER_VERSION="latest"
VOLUMES = -v $(PWD):/app

docker_shell = docker run --rm -it $(VOLUMES) $(DOCKER_REPO):dev /bin/ash -c $(1)

define PRINT_HELP_PYSCRIPT
import re, sys

for line in sys.stdin:
	match = re.match(r'^([a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-20s %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT

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

run: build ## Run in docker container
	docker run --rm -p 9540:9540 ${DOCKER_REPO}:${DOCKER_VERSION}

test: build_dev ## Run tests and coverage
	$(docker_shell) "coverage run -m pytest && coverage report"

static_analysis: build_dev ## Run mypy 
	$(docker_shell) "mypy ."

lint: build_dev ## Run flake8
	$(docker_shell) "flake8"

tests: static_analysis lint test ##  Run test and lint and static_analysis

format: build_dev ## Apply black + isort formatting 
	$(docker_shell) "black ."
	$(docker_shell) "isort ."

sh: build_dev ## Shell into development container
	$(docker_shell) /bin/ash

help: ## Print this help
	@python -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)
          
