---
name: ark-image-editor
description: Generate new raster images and edit existing image files with Volcengine Ark (Doubao-Seedream 4.5). Use when Codex needs to (1) create a brand-new image, illustration, photo, texture, sprite, or mockup from a text prompt, or (2) transform an existing local image file such as replacing or removing the background, changing art style, relighting, changing weather or time of day, adding or removing objects, or retouching a photo or illustration. Also use this skill as the image generation and editing path when the built-in imagegen tool is unavailable in the current session. Do not use it for SVG, vector, icon, or code-native assets that are better edited directly as text.
---

# Ark Image Editor

Generate and edit images through the Volcengine Ark API with the Doubao-Seedream 4.5 model. This skill is the working replacement for the built-in image generation and editing tool.

## Requirements

- `ARK_API_KEY` must already be set in the environment. Never ask the user for it and never print it.
- Use the bundled Python interpreter. Plain `python` on this machine can resolve to an unrelated toolchain, so prefer:
  `C:\Users\liaohanyi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`
- The calls reach the internet. If the sandbox blocks the request, rerun the same command with network permission.
- Default model: `doubao-seedream-4-5-251128` (Doubao-Seedream 4.5). Override with `ARK_IMAGE_ENDPOINT_ID` to use your own `ep-...` endpoint, or with `--model`.

## Run the script

The script lives next to this file at `scripts/ark_image_editor.py`. Put every flag after the subcommand.

Edit an existing image:

```
"C:\Users\liaohanyi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" "C:\Users\liaohanyi\.codex\skills\ark-image-editor\scripts\ark_image_editor.py" edit --input "D:\path\source.jpg" --prompt "Keep the character unchanged; replace the background with a pure blue starfield." --output "D:\path\source_starfield.png"
```

Generate a new image:

```
"C:\Users\liaohanyi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" "C:\Users\liaohanyi\.codex\skills\ark-image-editor\scripts\ark_image_editor.py" generate --prompt "A quiet rainy alley in Shanghai at night, cinematic photo." --output "D:\path\alley.png"
```

## Write prompts for edits

- Pass the user's instruction through as the prompt, then add an explicit preservation clause. State what must stay identical: character identity, face, hairstyle, pose, clothing details, silhouette and edge quality, subject lighting direction, and the subject's own colors.
- State what changes in the same sentence, so the model cannot reinterpret the whole image: name the new background, style, or region.
- Do not invent extra changes. One request, one change set.
- Repeat `--input` to pass more than one reference image; the first one plus the prompt drives the edit.
- `--input` also accepts an `http(s)` URL or a `data:` URI.

For example, a background swap prompt should read like: "Keep the character completely unchanged, including pose, colors, linework and edges; replace only the background with a pure blue starfield, matching the original lighting on the character."

## Output behavior

- Without `--output`, `edit` writes `<input name>_edited.png` next to the input file, and `generate` writes `ark_image_<timestamp>.png` in the current directory.
- The script sniffs the returned bytes and corrects the file extension to the real format, so a requested `.png` can come back as `.jpg`. Trust the path the script prints.
- Existing files are never overwritten. The script appends `-1`, `-2` and so on. Pass `--overwrite` only when the user asks for it.
- The script prints the absolute path of every file it writes. Report that path to the user. Do not re-encode or rename the output afterwards.

## Flags

- `--size`: `2048x2048` by default; also accepts `2K`, `4K`, or an explicit `WIDTHxHEIGHT`. Ark rejects anything under 3,686,400 total pixels, so `1024x1024` fails.
- `--response-format`: `url` (default) or `b64_json`; the script writes the same file either way.
- `--n`: request more than one image; results get numeric suffixes.
- `--seed`, `--guidance-scale`: optional determinism and prompt-adherence controls.
- `--watermark`: off by default. Leave it off unless the user asks for a watermark.
- `--dry-run`: print the JSON payload without calling the API; use it to check argument wiring.
- `--timeout`: per-request timeout in seconds, default 300.
- Transient `ServerOverloaded` (HTTP 429) and 5xx responses are retried up to three times with backoff. If it still fails, wait and run the same command again; do not change the prompt on a retry.

## Verify the result

1. Confirm the command printed a path and the file exists with a non-zero size.
2. Open the produced image and compare it with the source. Confirm the requested change is visible and the preserved subject is unchanged.
3. If the model changed too much, or the subject drifted, rerun with a tighter prompt and the same input rather than editing the output image again.
4. On failure the script prints the Ark error payload. Read the reported field or parameter name and correct that argument instead of guessing.

## Report back

Give the user the absolute path of the generated image and show it inline with a Markdown image tag. Mention the model, size, and the prompt that produced it, plus anything that visibly did not match the request.
