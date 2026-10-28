# Machine-specific registry overrides

Create a repository-local `local/` directory for private configuration. That directory is gitignored.

`backend/app/registry.py` merges `local/models_registry.local.yaml` into the model registry when the file exists. Follow the structure of `backend/models_registry.yaml` and the registry loader when preparing an override.

Keep machine paths, local notes, and credentials out of shared configuration. Do not commit private model/input paths. A registry entry alone does not install weights or validate its workflow.

See the [root README](../README.md) and [contribution guide](../CONTRIBUTING.md).
