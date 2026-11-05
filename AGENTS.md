# AGENTS.md

Guidance for AI coding agents working in this repository or using shortstock as a tool.

## Using shortstock

Use the CLI with `--json`. Start with `shortstock doctor --json`, then `shortstock make <script.md or -> --json --out <dir>`. The full workflow is in [skills/shortstock/SKILL.md](skills/shortstock/SKILL.md). Only run `shortstock publish` when the user explicitly asks to post to their social accounts.

## Codebase map

- `src/shortstock/pipeline.py`: the four stages (voice, plan, footage, render) and the runner. Each stage saves `<SHORTSTOCK_HOME>/runs/<id>/work/<stage>.json`; a retry skips stages whose file exists.
- `script.py`: parses scripts (headings, `[visual: ...]` hints, `[clip: id]` locks, Markdown) with character offsets, which the web storyboard uses to edit directions in place.
- `tts.py`: ElevenLabs and Fish Audio clients with word timestamps, chunking for long scripts.
- `plan.py`: matches sentences to spoken words, writes footage searches (hint, optional LLM, keywords) and splits shots.
- `footage.py`: Pexels search and the local stock bank.
- `render.py`, `captions.py`: ffmpeg assembly, music ducking and ASS captions.
- `llm.py`: optional OpenAI-compatible client (OpenRouter). `publish.py`: Buffer and S3.
- `db.py`, `config.py`, `api.py`, `worker.py`, `cli.py`: storage, settings, HTTP API, queue worker and command line.
- `frontend/`: React + Vite + Tailwind web app (Studio: script sheet plus live storyboard; Library; Video; Settings). `npm run build` writes into `src/shortstock/web`. `src/scriptEdits.ts` writes storyboard choices back into the script.

## Conventions

- Run `uv run pytest -q` and `uv run ruff check src tests` before finishing. Tests need ffmpeg but no network or API keys.
- Keep modules small and dependencies few.
- Never commit API keys or files from `SHORTSTOCK_HOME`.

Never call `ffmpeg` or `ffprobe` by name: use `media.ffmpeg_bin()` / `media.ffprobe_bin()`. On macOS the ffmpeg that can draw captions is Homebrew's keg-only `ffmpeg-full`, which is not on the PATH.
