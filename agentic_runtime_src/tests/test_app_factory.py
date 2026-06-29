from agentic_runtime.server import RuntimeServer
from runtime_test_helpers import create_test_runtime_server


def test_app_factory_lists_and_validates_template_agent():
    server = create_test_runtime_server()
    apps = {record["app_id"] for record in server.app_factory.list_apps()}

    assert "app_template" in apps
    assert "color_block_grasper_agent" in apps
    assert "inspection_agent" not in apps
    manifest = server.app_factory.validate_app("app_template")
    assert manifest.name == "app_template"
