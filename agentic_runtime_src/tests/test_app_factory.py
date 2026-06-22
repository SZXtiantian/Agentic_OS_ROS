from agentic_runtime.server import RuntimeServer
from runtime_test_helpers import create_test_runtime_server


def test_app_factory_lists_and_validates_inspection_agent():
    server = create_test_runtime_server()
    apps = {record["app_id"] for record in server.app_factory.list_apps()}

    assert "inspection_agent" in apps
    manifest = server.app_factory.validate_app("inspection_agent")
    assert manifest.name == "inspection_agent"
