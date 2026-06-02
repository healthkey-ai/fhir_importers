FRONTEND_DIR := frontend
NODE_MODULES := $(FRONTEND_DIR)/node_modules

DEPLOY_HOST := cancerbot.app
DEPLOY_PATH := /apps/fhir-importers

.PHONY: ui ui-build pytest deploy

$(NODE_MODULES): $(FRONTEND_DIR)/package.json
	cd $(FRONTEND_DIR) && npm install
	@touch $(NODE_MODULES)

ui: $(NODE_MODULES)
	cd $(FRONTEND_DIR) && npm run dev

ui-build: $(NODE_MODULES)
	cd $(FRONTEND_DIR) && npm run build

pytest:
	@pip install -q -r requirements-dev.txt
	@python -m pytest

deploy:
	@echo "Deploying to $(DEPLOY_HOST)..."
	rsync -az --delete \
		--rsync-path="sudo rsync" \
		--exclude='.git/' \
		--exclude='venv/' \
		--exclude='$(FRONTEND_DIR)/node_modules/' \
		--exclude='$(FRONTEND_DIR)/dist/' \
		--exclude='__pycache__/' \
		--exclude='*.pyc' \
		--exclude='.idea/' \
		--exclude='*.tsbuildinfo' \
		./deploy/ $(DEPLOY_HOST):$(DEPLOY_PATH)/

