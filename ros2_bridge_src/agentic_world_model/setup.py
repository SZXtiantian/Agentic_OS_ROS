from setuptools import setup

package_name = "agentic_world_model"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", ["launch/world_model.launch.py"]),
    ],
    install_requires=["setuptools", "pyyaml"],
    zip_safe=True,
    maintainer="Agentic OS",
    maintainer_email="agentic@example.com",
    description="World model adapter for Agentic OS.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "world_model_node = agentic_world_model.world_model_node:main",
        ],
    },
)
