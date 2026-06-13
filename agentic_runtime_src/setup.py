from setuptools import find_packages, setup


setup(
    name="agentic-runtime",
    version="0.1.0",
    description="Agentic OS runtime MVP running above ROS2.",
    packages=find_packages("."),
    install_requires=[
        "pyyaml>=6",
        "jsonschema>=4",
    ],
    extras_require={
        "dev": [
            "pytest>=8",
        ],
    },
    python_requires=">=3.10",
)
