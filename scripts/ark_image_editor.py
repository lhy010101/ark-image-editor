#!/usr/bin/env python3
"""Generate or edit images with Volcengine Ark (Doubao-Seedream 4.5).

Subcommands:
    edit      image-to-image editing from one or more local image files
    generate  text-to-image generation

The ARK_API_KEY environment variable supplies the credential. The default
model is Doubao-Seedream 4.5 (doubao-seedream-4-5-251128); override it with
--model, or set ARK_IMAGE_ENDPOINT_ID to use your own Ark inference endpoint.

Only the standard library is required, so the script runs with any Python 3.8+
interpreter, including the bundled Codex runtime.
"""

from __future__ import annotations

import argparse
import base64
import datetime
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL = "doubao-seedream-4-5-251128"
DEFAULT_SIZE = "2048x2048"
DEFAULT_RESPONSE_FORMAT = "url"
DEFAULT_TIMEOUT = 300.0
DEFAULT_EXTENSION = ".png"
RETRY_STATUS = (429, 500, 502, 503, 504)
MAX_ATTEMPTS = 3

MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}

MAGIC_SIGNATURES = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"BM", ".bmp"),
    (b"II*\x00", ".tif"),
    (b"MM\x00*", ".tif"),
)


def log(message):
    print(message, file=sys.stderr, flush=True)


def detect_extension(payload):
    """Identify the real container from the image bytes, or None if unknown."""
    if payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return ".webp"
    for signature, extension in MAGIC_SIGNATURES:
        if payload.startswith(signature):
            return extension
    return None


def matches_format(suffix, detected):
    suffix = suffix.lower()
    if detected == ".jpg":
        return suffix in (".jpg", ".jpeg")
    if detected == ".tif":
        return suffix in (".tif", ".tiff")
    return suffix == detected


def encode_image_argument(raw):
    """Return an API-ready image value: a URL, a data URI, or local base64."""
    if raw.startswith(("http://", "https://", "data:")):
        return raw
    path = Path(raw).expanduser()
    if not path.is_file():
        raise SystemExit("[error] input image not found: {0}".format(path))
    mime = MIME_BY_SUFFIX.get(path.suffix.lower())
    if not mime:
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    log("[info] attached {0} ({1} bytes, {2})".format(path, path.stat().st_size, mime))
    return "data:{0};base64,{1}".format(mime, payload)


def with_extension(path):
    if path.suffix:
        return path
    return path.with_suffix(DEFAULT_EXTENSION)


def unique_path(path):
    """Return path, or the first free path-1, path-2 ... variant of it."""
    if not path.exists():
        return path
    for index in range(1, 1000):
        candidate = path.with_name("{0}-{1}{2}".format(path.stem, index, path.suffix))
        if not candidate.exists():
            return candidate
    raise SystemExit("[error] cannot find a free filename near {0}".format(path))


def describe_error(raw):
    text = raw.decode("utf-8", "replace").strip()
    try:
        data = json.loads(text)
    except ValueError:
        return text
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            code = error.get("code") or error.get("type") or ""
            message = error.get("message") or json.dumps(error, ensure_ascii=False)
            return "{0}: {1}".format(code, message).strip(": ")
        if isinstance(error, str):
            return error
        if data.get("message"):
            return str(data["message"])
    return json.dumps(data, ensure_ascii=False)


def post_json(url, payload, api_key, timeout):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    log("[info] POST {0}".format(url))
    for attempt in range(1, MAX_ATTEMPTS + 1):
        request = urllib.request.Request(url, data=body, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json")
        request.add_header("Authorization", "Bearer {0}".format(api_key))
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = describe_error(exc.read()) or str(exc.reason)
            if exc.code in RETRY_STATUS and attempt < MAX_ATTEMPTS:
                delay = 3.0 * attempt
                log(
                    "[warn] HTTP {0} from Ark ({1}); attempt {2}/{3}, retrying in {4:.0f}s".format(
                        exc.code, detail, attempt, MAX_ATTEMPTS, delay
                    )
                )
                time.sleep(delay)
                continue
            raise SystemExit("[error] HTTP {0} from Ark: {1}".format(exc.code, detail))
        except urllib.error.URLError as exc:
            if attempt < MAX_ATTEMPTS:
                delay = 3.0 * attempt
                log(
                    "[warn] network failure ({0}); attempt {1}/{2}, retrying in {3:.0f}s".format(
                        exc.reason, attempt, MAX_ATTEMPTS, delay
                    )
                )
                time.sleep(delay)
                continue
            raise SystemExit("[error] network failure calling Ark: {0}".format(exc.reason))
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise SystemExit("[error] Ark returned a non-JSON response: {0!r}".format(raw[:500]))


def download_image(url, api_key, timeout):
    """Fetch the generated asset, retrying with credentials for private URLs."""
    for with_credentials in (False, True):
        request = urllib.request.Request(url, method="GET")
        if with_credentials:
            request.add_header("Authorization", "Bearer {0}".format(api_key))
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if not with_credentials and exc.code in (401, 403):
                log("[info] retrying download with credentials (HTTP {0})".format(exc.code))
                continue
            raise SystemExit("[error] failed to download image (HTTP {0})".format(exc.code))
        except urllib.error.URLError as exc:
            raise SystemExit("[error] failed to download image: {0}".format(exc.reason))
    raise SystemExit("[error] failed to download image after retrying with credentials")


def extract_results(response):
    """Return a list of ("b64", payload) / ("url", address) tuples."""
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, list) or not data:
        summary = json.dumps(response, ensure_ascii=False)[:500]
        raise SystemExit("[error] Ark response contained no image: {0}".format(summary))
    results = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if item.get("b64_json"):
            results.append(("b64", item["b64_json"]))
        elif item.get("url"):
            results.append(("url", item["url"]))
    if not results:
        raise SystemExit("[error] Ark returned no usable image field (url/b64_json)")
    return results


def save_results(results, base_output, api_key, timeout, overwrite):
    written = []
    for index, (kind, value) in enumerate(results):
        target = base_output
        if len(results) > 1:
            target = base_output.with_name(
                "{0}-{1}{2}".format(base_output.stem, index + 1, base_output.suffix)
            )
        if not overwrite:
            target = unique_path(target)
        payload = base64.b64decode(value) if kind == "b64" else download_image(value, api_key, timeout)
        if not payload:
            raise SystemExit("[error] empty image payload for {0}".format(target))
        detected = detect_extension(payload)
        if detected and not matches_format(target.suffix, detected):
            target = target.with_suffix(detected)
            if not overwrite:
                target = unique_path(target)
            log(
                "[info] Ark returned {0} data; saving as {1}".format(
                    detected.lstrip(".").upper(), target.name
                )
            )
        target.write_bytes(payload)
        log("[ok] wrote {0} ({1} bytes)".format(target, len(payload)))
        written.append(target)
    return written


def resolve_edit_output(raw_output, first_input):
    if raw_output:
        return with_extension(Path(raw_output).expanduser().resolve())
    source = Path(first_input).expanduser().resolve()
    return source.with_name("{0}_edited{1}".format(source.stem, DEFAULT_EXTENSION))


def resolve_generate_output(raw_output):
    if raw_output:
        return with_extension(Path(raw_output).expanduser().resolve())
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path.cwd() / "ark_image_{0}{1}".format(stamp, DEFAULT_EXTENSION)


def build_payload(args, image_values):
    payload = {
        "model": args.model,
        "prompt": args.prompt,
        "size": args.size,
        "response_format": args.response_format,
        "watermark": bool(args.watermark),
    }
    if image_values:
        payload["image"] = image_values
    if args.n and args.n > 1:
        payload["n"] = args.n
    if args.seed is not None:
        payload["seed"] = args.seed
    if args.guidance_scale is not None:
        payload["guidance_scale"] = args.guidance_scale
    return payload


def redact_payload(payload):
    redacted = dict(payload)
    images = redacted.get("image")
    if isinstance(images, list):
        redacted["image"] = [
            value[:64] + "...<truncated>" if isinstance(value, str) and len(value) > 64 else value
            for value in images
        ]
    return redacted


def run(args):
    api_key = args.api_key or os.environ.get("ARK_API_KEY")
    if not api_key:
        raise SystemExit("[error] ARK_API_KEY is not set; pass --api-key or export it")
    if args.n is not None and args.n < 1:
        raise SystemExit("[error] --n must be at least 1")

    image_values = [encode_image_argument(item) for item in args.inputs] if args.command == "edit" else []
    payload = build_payload(args, image_values)
    url = "{0}/images/generations".format(args.base_url.rstrip("/"))

    if args.dry_run:
        print(json.dumps(redact_payload(payload), ensure_ascii=False, indent=2))
        return 0

    if args.command == "edit":
        output = resolve_edit_output(args.output, args.inputs[0])
    else:
        output = resolve_generate_output(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    log("[info] model={0} size={1} command={2}".format(args.model, args.size, args.command))
    response = post_json(url, payload, api_key, args.timeout)
    written = save_results(extract_results(response), output, api_key, args.timeout, args.overwrite)
    for path in written:
        print(path)
    return 0


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--prompt", required=True, help="Text instruction for the model.")
    common.add_argument("--output", help="Output file path; defaults to a generated name.")
    common.add_argument(
        "--model",
        default=os.environ.get("ARK_IMAGE_ENDPOINT_ID") or DEFAULT_MODEL,
        help="Ark model or endpoint id.",
    )
    common.add_argument(
        "--base-url",
        default=os.environ.get("ARK_BASE_URL") or DEFAULT_BASE_URL,
        help="Ark API base url.",
    )
    common.add_argument("--api-key", help="Ark API key; defaults to ARK_API_KEY.")
    common.add_argument(
        "--size",
        default=DEFAULT_SIZE,
        help="Output size, e.g. 2048x2048, 2K, 4K; Ark requires at least 3686400 total pixels.",
    )
    common.add_argument(
        "--response-format",
        default=DEFAULT_RESPONSE_FORMAT,
        choices=["url", "b64_json"],
        help="How Ark returns the generated image.",
    )
    common.add_argument("--watermark", action="store_true", help="Ask Ark to add a watermark.")
    common.add_argument("--n", type=int, default=1, help="Number of images to request.")
    common.add_argument("--seed", type=int, help="Deterministic seed.")
    common.add_argument("--guidance-scale", type=float, help="Prompt adherence strength.")
    common.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Per-request timeout.")
    common.add_argument("--overwrite", action="store_true", help="Allow overwriting an existing file.")
    common.add_argument("--dry-run", action="store_true", help="Print the request payload and stop.")

    parser = argparse.ArgumentParser(
        prog="ark_image_editor",
        description="Generate or edit images with Volcengine Ark (Doubao-Seedream 4.5).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    edit = subparsers.add_parser(
        "edit",
        parents=[common],
        help="Edit existing image(s) with a text instruction.",
        description="Edit one or more existing images (background replacement, restyle, retouch).",
    )
    edit.add_argument(
        "--input",
        dest="inputs",
        action="append",
        required=True,
        metavar="PATH_OR_URL",
        help="Reference image; repeat the flag for multiple references.",
    )

    generate = subparsers.add_parser(
        "generate",
        parents=[common],
        help="Generate a new image from a text prompt.",
        description="Generate a new image from a text prompt.",
    )
    generate.set_defaults(inputs=[])

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
