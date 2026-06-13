from setuptools import setup

package_name = "agentic_app_runtime_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml", "README.md"]),
        ("share/" + package_name + "/launch", ["launch/runtime_bridge.launch.py"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Agentic OS",
    maintainer_email="agentic@example.com",
    description="Optional Runtime aggregation bridge skeleton for Agentic OS.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "runtime_bridge_node = agentic_app_runtime_bridge.runtime_bridge_node:main",
        ],
    },
)
