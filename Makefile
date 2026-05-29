FRONTEND_DIR := frontend
NODE_MODULES := $(FRONTEND_DIR)/node_modules

DEPLOY_HOST := cancerbot.app
DEPLOY_PATH := ~/fhir-importers

.PHONY: ui ui-build deploy

$(NODE_MODULES): $(FRONTEND_DIR)/package.json
	cd $(FRONTEND_DIR) && npm install
	@touch $(NODE_MODULES)

ui: $(NODE_MODULES)
	cd $(FRONTEND_DIR) && npm run dev

ui-build: $(NODE_MODULES)
	cd $(FRONTEND_DIR) && npm run build

deploy:
	@echo "Deploying to $(DEPLOY_HOST)..."
	rsync -az --delete \
		--exclude='.git/' \
		--exclude='venv/' \
		--exclude='$(FRONTEND_DIR)/node_modules/' \
		--exclude='$(FRONTEND_DIR)/dist/' \
		--exclude='__pycache__/' \
		--exclude='*.pyc' \
		--exclude='.idea/' \
		--exclude='*.tsbuildinfo' \
		./ $(DEPLOY_HOST):$(DEPLOY_PATH)/
	ssh $(DEPLOY_HOST) "cd $(DEPLOY_PATH) && docker-compose up -d --build"
