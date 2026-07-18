---
title: Contributing
description: Help improve QuickEdit safely and predictably.
---

QuickEdit welcomes bug reports, documentation corrections, tests, and focused
feature proposals. Read the repository's [contribution guide](https://github.com/idityaGE/quick-edit/blob/main/CONTRIBUTING.md) and [code of conduct](https://github.com/idityaGE/quick-edit/blob/main/CODE_OF_CONDUCT.md) before participating.

## Development checks

```bash
uv sync --all-extras
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest --cov
```

Use mocked providers and generated local media fixtures in tests. Never add API
keys, personal recordings, or downloaded model artifacts to a pull request.
