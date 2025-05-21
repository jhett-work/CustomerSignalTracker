.PHONY: install run test clean

install:
	pip install -r requirements.txt

run:
	python -m cdp_signal_scanner.main $(ARGS)

test:
	pytest

clean:
	rm -rf __pycache__
	rm -rf cdp_signal_scanner/__pycache__
	rm -rf cdp_signal_scanner/data_sources/__pycache__
	rm -rf tests/__pycache__
	rm -f signals.csv
