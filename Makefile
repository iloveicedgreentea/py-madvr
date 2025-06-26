.PHONY: test dev_install build upload

dev_install:
	python3 -m venv .venv
	. .venv/bin/activate && \
	pip3 install -r requirements-test.txt

test:
	. .venv/bin/activate && pytest -s tests

upload: build
	twine upload dist/*

build:
	rm -rf dist/*
	python3 -m build
