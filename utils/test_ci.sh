#!/bin/sh

run_tests_with_coverage() {
  python -m coverage run --source /scratch/flexpart_ifs_utils/ --data-file test_reports/.coverage --module pytest --capture=tee-sys -vvv -rA --junitxml=test_reports/junit.xml test/
  python -m coverage xml --data-file test_reports/.coverage -o test_reports/coverage.xml
}

run_pylint() {
  python -m pylint --output-format=parseable --exit-zero /scratch/flexpart_ifs_utils/ | tee test_reports/pylint.log
}


run_mypy() {
  mypy -p flexpart_ifs_utils | grep error | tee test_reports/mypy.log
}

run_ci_tools() {
  run_tests_with_coverage && run_pylint && run_mypy
}
