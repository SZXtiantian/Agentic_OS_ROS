# 如何贡献

贡献文档时请保持以下原则：

- API 页面按固定模板编写：用途、签名、参数、返回、权限、错误、示例。
- 中文和英文路径保持一致。
- 不写“模拟成功”或“mock 成功路径”。
- 所有机器人动作描述都必须经过 Runtime permission、lock、safety 和 audit。
- 新增 SDK 方法时同步更新 `gitbook/SUMMARY.md`。

提交前运行：

```bash
python scripts/check_agentic_app_boundaries.py agentic_apps
PYTHONPATH=agentic_runtime_src pytest -q agentic_runtime_src/tests/test_docs_do_not_overclaim_capabilities.py agentic_runtime_src/tests/test_docs_real_only_contracts.py
```
