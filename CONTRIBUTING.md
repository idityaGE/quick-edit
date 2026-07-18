# Contributing to QuickEdit

Thanks for helping improve QuickEdit. For questions and proposals, use GitHub
Discussions; use Issues for reproducible bugs and scoped, actionable requests.

## Development setup

Install Python 3.11+, FFmpeg/FFprobe, and [uv](https://docs.astral.sh/uv/), then:

```bash
uv sync --all-extras
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest --cov
```

Run `npm ci` and `npm run build` in `website/` when changing documentation.

## Pull requests

- Keep each pull request focused and include tests for behavior changes.
- Do not commit videos, model weights, generated output, API keys, or `.env` files.
- Use mocked provider calls in tests; CI must not need paid services or secrets.
- Update the documentation and changelog when users will observe a change.
- By contributing, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
