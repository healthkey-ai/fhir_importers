FRONTEND_DIR := frontend
NODE_MODULES := $(FRONTEND_DIR)/node_modules

.PHONY: ui ui-build

$(NODE_MODULES): $(FRONTEND_DIR)/package.json
	cd $(FRONTEND_DIR) && npm install
	@touch $(NODE_MODULES)

ui: $(NODE_MODULES)
	cd $(FRONTEND_DIR) && npm run dev

ui-build: $(NODE_MODULES)
	cd $(FRONTEND_DIR) && npm run build
