# ark-image-editor

Generate and edit images from the command line or from an AI coding agent, using the
[Volcengine Ark](https://www.volcengine.com/product/ark) image API and the **Doubao-Seedream 4.5** model.

One small, dependency-free Python script covers both directions:

- `generate` - text to image.
- `edit` - image to image: background replacement, restyle, relighting, retouching, adding or removing objects.

The repository is also a [Codex Skill](https://github.com/openai/codex) (`SKILL.md`), so an agent can pick it up
automatically and drive it on your behalf. Nothing about the skill depends on Codex - the script is a normal CLI
you can call from a shell, a Makefile, or another automation.

## Features

- **No third-party dependencies.** Standard library only (`urllib`, `base64`, `json`), so it runs anywhere
  Python 3.8+ exists. No `requests`, no vendor SDK.
- **Both Ark response modes.** Decodes `b64_json` payloads and downloads `url` results, retrying with credentials
  when the returned URL is private.
- **Correct file extensions.** The script sniffs the returned bytes and fixes the extension for you, because Ark
  returns JPEG data even when you ask for a `.png` output path.
- **Never overwrites.** Existing files are preserved and the output is uniquified as `name-1.jpg`, `name-2.jpg`;
  pass `--overwrite` to opt out.
- **Retries overload.** HTTP 429 (`ServerOverloaded`) and 5xx responses are retried three times with backoff.
- **Readable failures.** Ark's own error payload is printed verbatim instead of a generic traceback.

## Requirements

- Python 3.8 or newer.
- A Volcengine Ark API key, provided through the `ARK_API_KEY` environment variable.
- A Seedream model id, or your own Ark inference endpoint id (`ep-...`).
- Network access to `https://ark.cn-beijing.volces.com`.

## Install

### As a Codex skill

```bash
git clone https://github.com/lhy010101/ark-image-editor.git ~/.codex/skills/ark-image-editor
```

Windows (PowerShell):

```powershell
git clone https://github.com/lhy010101/ark-image-editor.git "$env:USERPROFILE\.codex\skills\ark-image-editor"
```

Restart or refresh Codex so the skill is discovered, then ask for an image in plain language or reference
`$ark-image-editor` explicitly.

### As a standalone CLI

```bash
git clone https://github.com/lhy010101/ark-image-editor.git
cd ark-image-editor
python scripts/ark_image_editor.py --help
```

## Configuration

macOS / Linux:

```bash
export ARK_API_KEY="your-ark-api-key"
```

Windows PowerShell:

```powershell
$env:ARK_API_KEY = "your-ark-api-key"   # current session
setx ARK_API_KEY "your-ark-api-key"     # persist for future sessions
```

Optional overrides:

| Variable | Purpose | Default |
| --- | --- | --- |
| `ARK_IMAGE_ENDPOINT_ID` | Your own Ark inference endpoint id (`ep-...`) | unset |
| `ARK_BASE_URL` | Ark API base URL | `https://ark.cn-beijing.volces.com/api/v3` |

The key is read from the environment on every run. It is never written to disk, never logged, and never embedded
in a request URL.

## Usage

Put every flag after the subcommand.

### Generate an image

```bash
python scripts/ark_image_editor.py generate \
  --prompt "A quiet rainy alley in Shanghai at night, cinematic photo" \
  --output out/alley.png
```

### Edit an existing image

```bash
python scripts/ark_image_editor.py edit \
  --input input/character.jpg \
  --prompt "Keep the character completely unchanged (pose, colors, linework, silhouette edges, lighting). Replace only the background with a plain deep-blue starfield full of stars." \
  --output out/character_starfield.png
```

State what must stay identical as well as what should change. A preservation clause such as
"keep the subject completely unchanged, replace only the background" is what stops the model from redrawing the
whole picture.

Repeat `--input` to pass several references. Each value may be a local file, an `http(s)` URL, or a `data:` URI:

```bash
python scripts/ark_image_editor.py edit \
  --input base.png \
  --input style-reference.png \
  --prompt "Apply the rendering style of the second image to the first, keeping its composition intact." \
  --output out/styled.png
```

### Inspect a request without spending a call

```bash
python scripts/ark_image_editor.py edit --input character.jpg --prompt "..." --dry-run
```

`--dry-run` prints the JSON payload that would be sent, with image data truncated, and exits without contacting Ark.

### Options

| Flag | Description |
| --- | --- |
| `--prompt` | Required. Instruction for the model. |
| `--input` | `edit` only, repeatable. Reference image path, URL, or `data:` URI. |
| `--output` | Output path. Defaults to `<input>_edited.png` for `edit`, `ark_image_<timestamp>.png` for `generate`. |
| `--size` | `2048x2048` by default. Also accepts `2K`, `4K`, or an explicit `WIDTHxHEIGHT`. |
| `--model` | Model or endpoint id. Defaults to `ARK_IMAGE_ENDPOINT_ID`, else `doubao-seedream-4-5-251128`. |
| `--base-url` | Ark API base URL. Defaults to `ARK_BASE_URL`, else the Beijing endpoint. |
| `--api-key` | Overrides `ARK_API_KEY`. Prefer the environment variable. |
| `--response-format` | `url` (default) or `b64_json`. |
| `--n` | Request more than one image; results get numeric suffixes. |
| `--seed` | Deterministic generation seed. |
| `--guidance-scale` | Prompt adherence strength. |
| `--watermark` | Ask Ark to add a watermark. Off by default. |
| `--timeout` | Per-request timeout in seconds. Defaults to `300`. |
| `--overwrite` | Allow overwriting an existing output file. |
| `--dry-run` | Print the request payload and exit. |

## The 3,686,400 pixel minimum (why `1024x1024` fails)

Ark rejects any `size` below **3,686,400 total pixels**, which is exactly 1920 x 1920 - roughly 3.69 million
pixels. This is the first thing most people hit, because `1024x1024` is the conventional default everywhere else:

```
HTTP 400 from Ark: InvalidParameter: The parameter `size` specified in the request is not valid:
image size must be at least 3686400 pixels.
```

This script therefore defaults to `2048x2048` (4,194,304 pixels).

| Size | Total pixels | Result |
| --- | --- | --- |
| `1024x1024` | 1,048,576 | rejected |
| `1600x1600` | 2,560,000 | rejected |
| `1920x1920` | 3,686,400 | minimum accepted |
| `2400x1600` | 3,840,000 | accepted |
| `2048x2048` | 4,194,304 | default |
| `2K`, `4K` | provider presets | accepted |

When editing a non-square source, pick a size that matches its aspect ratio and still clears the minimum, for
example `--size 2400x1600` for a 3:2 image.

## Output behaviour

- `edit` without `--output` writes `<input name>_edited.png` next to the input file.
- `generate` without `--output` writes `ark_image_<timestamp>.png` into the current directory.
- The real container wins: if Ark returns JPEG bytes for a requested `.png` path, the file is saved as `.jpg`.
  Always trust the absolute path the script prints.
- The script prints one absolute path per generated image on stdout; progress and errors go to stderr.

## Repository layout

```
ark-image-editor/
  SKILL.md                     # Codex skill definition (trigger conditions + usage rules)
  README.md
  LICENSE
  agents/openai.yaml           # UI metadata for the skill list
  scripts/ark_image_editor.py  # the CLI
```

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `ARK_API_KEY is not set` | Export the variable, or pass `--api-key`. |
| `HTTP 400 ... image size must be at least 3686400 pixels` | Raise `--size`; see the section above. |
| `HTTP 429 ... ServerOverloaded` | Transient capacity issue. The script retries three times with backoff; if it still fails, wait and repeat the identical command. |
| `HTTP 404` / endpoint not found | Your endpoint id belongs to another account, or the model name is wrong. Set `ARK_IMAGE_ENDPOINT_ID` or pass `--model`. |
| Output looks nothing like the input | The prompt was too open. Restate the change narrowly and add an explicit preservation clause. |

## Security

The API key is read from `ARK_API_KEY` (or `--api-key`) at runtime and is only ever sent in the `Authorization`
header to the configured base URL. No credential is hardcoded, committed, logged, or returned in `--dry-run`
output.

## License

[MIT](LICENSE)

This project is not affiliated with, endorsed by, or sponsored by Volcengine or ByteDance.
