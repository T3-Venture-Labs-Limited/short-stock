---
name: shortstock
description: Turn a script into a narrated stock-footage video (faceless video) with the shortstock CLI. Use when the user asks to make a voiceover video, a faceless short, a YouTube/TikTok explainer from a script, or to turn text into a video with stock footage and captions.
---

# shortstock

shortstock is a local CLI that voices a script with ElevenLabs or Fish Audio, matches Pexels stock footage to every sentence, and renders a captioned MP4.

## Before the first run

```bash
shortstock doctor --json
```

Every check with `"required": true` must be `"ok": true`. If keys are missing, ask the user for them and save them; never print or log keys:

```bash
shortstock config set elevenlabs_api_key <key>     # or fish_api_key + fish_voice_id, and tts_provider fish
shortstock config set pexels_api_key <key>
```

## Write the script

- Plain text or Markdown. Write for the ear: short sentences, one idea each. About 160 words is a one-minute video.
- A Markdown heading is not spoken and becomes the title.
- Put `[visual: concrete filmable search terms]` before a sentence to choose its footage, for example `[visual: hands typing on laptop]`. Use English terms, no brand names or named people.
- To lock an exact clip, run `shortstock footage "<search>" --json`, look at the `image` thumbnails, and put `[clip: <id>]` before the sentence.

## Make the video

```bash
shortstock make script.md --json --out <folder>
cat script.md | shortstock make - --json --out <folder>
```

Useful options: `--voice elevenlabs:<voice_id>` or `--voice fish:<voice_id>`, `--aspect 9:16|4:5|1:1|16:9`, `--style bold|highlight|minimal`, `--no-captions`, `--max-shot 3.5`, `--speed 1.0`, `--music file.mp3`, `--title`, `--caption`, `--hashtags "#a #b"`.

The command prints progress to stderr and JSON to stdout:

```json
{"run_id": "…", "status": "completed", "video": {"id": "…", "file": "/abs/path/video.mp4", "duration_seconds": 18.8}, "credits": [ … ]}
```

The exit code is 0 when the video was made. On failure, `error` names the stage. Fix the cause and resume:

```bash
shortstock retry <run_id> --json                  # resume
shortstock retry <run_id> --from footage --json   # new footage, same voiceover
```

## Other commands

- `shortstock voices --provider elevenlabs --json`, `shortstock voices --provider fish --search <term> --json`
- `shortstock runs --json`, `shortstock show <run_id> --json`
- `shortstock channels --json` and `shortstock publish <video_id> --channel <id> --mode queue|schedule|now|draft [--at ISO]` (publishing posts to the user's real accounts; only when explicitly asked)
