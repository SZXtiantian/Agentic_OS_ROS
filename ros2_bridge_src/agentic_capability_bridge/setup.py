from glob import glob

from setuptools import setup

package_name = "agentic_capability_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.py")),
    ],
    install_requires=["setuptools", "pyyaml"],
    zip_safe=True,
    maintainer="Agentic OS",
    maintainer_email="agentic@example.com",
    description="Robot capability bridge adapters for Agentic OS.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "state_bridge_node = agentic_capability_bridge.state_bridge_node:main",
            "inspection_bridge_node = agentic_capability_bridge.inspection_bridge_node:main",
            "navigation_bridge_node = agentic_capability_bridge.navigation_bridge_node:main",
        ],
    },
)
