all:
	test -d dist && rm -rf dist
	mkdir dist
	cp -r . dist || exit 0
	python3 manifest.py --version 0.0.1
