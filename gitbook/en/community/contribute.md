# How to Contribute

Documentation contributions should follow these rules:

- API pages use the fixed template: purpose, signature, parameters, returns, permissions, errors, example.
- English and Chinese paths stay aligned.
- Do not document simulated success or mock success paths.
- Every robot action description must mention Runtime permission, lock, safety, and audit boundaries.
- Update `gitbook/SUMMARY.md` whenever adding SDK methods.

Before submitting:

```bash
python scripts/check_agentic_app_boundaries.py agentic_apps
PYTHONPATH=agentic_runtime_src pytest -q agentic_runtime_src/tests/test_docs_do_not_overclaim_capabilities.py agentic_runtime_src/tests/test_docs_real_only_contracts.py
```
