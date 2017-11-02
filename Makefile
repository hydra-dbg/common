.PHONY: all test 

all:
	echo "Usage: make test"
	exit 1

test:
	python${python_version} test/doctestpyjs.py `find regress/ -name '*.rst'`

clean:
	find . -name __pycache__ -exec rm -R {} \; || true
	find . -name "*.pyc" -exec rm -R {} \;
