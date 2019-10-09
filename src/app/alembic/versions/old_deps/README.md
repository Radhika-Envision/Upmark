## Frozen dependencies

This package contains old dependencies that were used by the legacy
model code. You should probably not add anything here. If you are
making a new revision, create a special package for your revision
in the parent directory called something like `model_1dbcbe2a1a6`,
where `1dbcbe2a1a6` is the Alembic revision ID. Then import it with:

```
import model_1dbcbe2a1a6 as frozen_model
```
