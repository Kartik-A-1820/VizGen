# Local private overrides (example)

Copy this folder to `local/` on your machine (the real `local/` directory is **gitignored**).

```text
mkdir local
copy local.example\README.md local\
# Then create:
#   local/PERSONAL_GENERATE.md
#   local/models_registry.local.yaml
```

Or let an agent recreate the private guide under `local/` (never commit it).

`backend/app/registry.py` loads `local/models_registry.local.yaml` if present and merges into the model dropdown **only on that machine**.
