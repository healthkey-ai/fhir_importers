FRONTEND_DIR := frontend
NODE_MODULES := $(FRONTEND_DIR)/node_modules

DEPLOY_HOST := cancerbot.app
DEPLOY_PATH := /apps/fhir-importers
SMOKE_URL   := https://healthkey-fhir-backend.cancerbot.org

.PHONY: ui ui-build pytest smoke deploy

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

smoke:
	@echo "→ $(SMOKE_URL)/remote/remoteEntry.js"
	@curl -fsSI $(SMOKE_URL)/remote/remoteEntry.js | head -1
	@echo "→ $(SMOKE_URL)/epic/organizations"
	@curl -fsS $(SMOKE_URL)/epic/organizations | python3 -c "import json,sys; o=json.load(sys.stdin); print(' ', len(o), 'orgs, first:', o[0]['alias'])"

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

