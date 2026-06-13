from setuptools import setup

package_name = "agentic_safety_guard"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", ["launch/safety_guard.launch.py"]),
    ],
    install_requires=["setuptools", "pyyaml"],
    zip_safe=True,
    maintainer="Agentic OS",
    maintainer_email="agentic@example.com",
    description="Safety guard adapter for Agentic OS.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "safety_guard_node = agentic_safety_guard.safety_guard_node:main",
        ],
    },
)
