.PHONY: all test 

all:
	echo "Usage: make test"
	exit 1

test:
	python test/run.py `find regress/ -name '*.rst'`

