#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
SOURCE_DIR="${REPO_ROOT}/native/lab"
BUILD_DIR="${SOURCE_DIR}/build"
BACKEND_DIR="${REPO_ROOT}/app/backend"
PYBIND11_DIR="$(python -m pybind11 --cmakedir)"

cmake \
  -S "${SOURCE_DIR}" \
  -B "${BUILD_DIR}" \
  -DCMAKE_BUILD_TYPE=Release \
  -Dpybind11_DIR="${PYBIND11_DIR}"

cmake --build "${BUILD_DIR}" --config Release --parallel "${CMAKE_BUILD_PARALLEL_LEVEL:-2}"
ctest --test-dir "${BUILD_DIR}" --output-on-failure
cmake --install "${BUILD_DIR}" --prefix "${BACKEND_DIR}"

python - <<'PY'
import medicore_lab
assert medicore_lab.CONTRACT_VERSION == "medicore-lab-v1"
print(f"Installed {medicore_lab.__name__} ({medicore_lab.CONTRACT_VERSION})")
PY
