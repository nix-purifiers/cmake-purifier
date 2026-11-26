# SPDX-License-Identifier: MIT
#
# A configure that installs a Python package with pip, as rocBLAS installs
# Tensile (cmake/virtualenv.cmake of rocBLAS): a virtual environment of the
# build's Python, and `pip install` of the local package demo. pip builds
# demo in an isolated environment, with the setuptools its pyproject.toml
# names, which it fetches from PyPI: the page of setuptools on the index
# and its wheel. The lock run locks them with pip-purifier's pypi-handler,
# which writes the page from the locked wheel.
cmake_minimum_required(VERSION 3.24)
project(purifier-pip-configure NONE)

find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(venv "${CMAKE_BINARY_DIR}/venv")
execute_process(
  COMMAND "${Python3_EXECUTABLE}" -m venv "${venv}" --system-site-packages --clear
  COMMAND_ERROR_IS_FATAL ANY)
execute_process(
  COMMAND "${venv}/bin/python" -m pip install "${CMAKE_CURRENT_SOURCE_DIR}/demo"
  COMMAND_ERROR_IS_FATAL ANY)
execute_process(
  COMMAND "${venv}/bin/python" -c "import demo; print(demo.VALUE)"
  OUTPUT_FILE "${CMAKE_BINARY_DIR}/value.txt"
  COMMAND_ERROR_IS_FATAL ANY)

install(FILES "${CMAKE_BINARY_DIR}/value.txt" DESTINATION share/purifier-pip-configure)
