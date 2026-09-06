from __future__ import annotations

import sys
from pathlib import Path

import pybind11
from setuptools import Extension, setup

ROOT = Path(__file__).resolve().parent

extra_compile_args = ["/std:c++20", "/O2"] if sys.platform == "win32" else ["-std=c++20", "-O3"]

setup(
    name="medicore-lab-native",
    version="1.1.0",
    description="MediCore native C++20 laboratory normalization, classification and clinical metrics core",
    ext_modules=[
        Extension(
            "medicore_lab",
            sources=[
                str(ROOT / "src" / "bindings.cpp"),
                str(ROOT / "src" / "lab_core.cpp"),
                str(ROOT / "src" / "clinical_metrics.cpp"),
            ],
            include_dirs=[
                pybind11.get_include(),
                str(ROOT / "include"),
            ],
            language="c++",
            extra_compile_args=extra_compile_args,
        )
    ],
    zip_safe=False,
)
