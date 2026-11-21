.PHONY: lint test build

lint:
	./scripts/lint.sh

test:
	python3 -m pytest tests

build:
	dotnet build backend/Forge.Api.csproj --nologo
	npm --prefix frontend run build
