# Contributing to shortstock

Thanks for helping. shortstock takes contributions through pull requests from forks. Nobody outside the maintainers pushes to this repository directly, and `main` only changes through reviewed pull requests.

## How to contribute

1. **Open an issue first for anything bigger than a small fix**, so we can agree on the approach before you spend time on it.
2. **Fork** the repository and create a branch from `main`.
3. Make your change, with tests where it makes sense.
4. Run the checks below until they pass.
5. **Open a pull request** against `main`. Describe what changed, why, and how you tested it. Add a screenshot for UI changes.

A maintainer reviews every pull request. CI must pass before it can be merged. Workflows on pull requests from first-time contributors start after a maintainer approves them.

## Development setup

Requires Python 3.11+, Node 22+, [uv](https://docs.astral.sh/uv/) and ffmpeg with libass.

```bash
uv sync
npm --prefix frontend ci
npm --prefix frontend run dev     # UI on :5173, proxies /api to :8000
uv run shortstock serve           # API and worker on :8000
```

[`AGENTS.md`](AGENTS.md) maps the codebase.

## Checks

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest -q
npm --prefix frontend test
npm --prefix frontend run build
```

For UI changes, click through the controls you touched at desktop width and at phone width (390 px) before opening the pull request.

## Guidelines

- Keep pull requests focused: one change per pull request.
- Match the existing style. The web app has its own visual identity; discuss larger design changes in an issue first.
- Never commit API keys, generated videos or personal data.
- By contributing you agree that your work is released under the [MIT licence](LICENSE).

## Your own version

shortstock is MIT licensed. You are welcome to fork it and take it in your own direction without contributing back.
