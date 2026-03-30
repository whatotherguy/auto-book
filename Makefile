PYTHON  := apps/api/.venv/Scripts/python.exe
API_DIR := apps/api
WEB_DIR := apps/web

.PHONY: api web dev install

api:
	cd $(API_DIR) && ../../$(PYTHON) -m uvicorn app.main:app --reload --port 8000

web:
	cd $(WEB_DIR) && npm run dev

install:
	cd $(API_DIR) && $(PYTHON) -m pip install -e .
	cd $(WEB_DIR) && npm install
