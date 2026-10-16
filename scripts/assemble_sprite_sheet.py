#!/usr/bin/env python3
"""Assemble independent transparent frames into a Godot sprite sheet."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - environment-dependent message
    raise SystemExit("This helper requires Pillow. Install Pillow, then rerun it.") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Place same-sized transparent frames inside an exact integer grid. "
            "By default, duplicate the first frame at the end for a loop."
        )
    )
    parser.add_argument("--frames", nargs="+", required=True, help="Independent PNG frames in playback order")
    parser.add_argument("--output", required=True, help="Output PNG path; existing files are never overwritten")
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--rows", type=int, default=1)
    parser.add_argument("--cell-width", type=int, default=1024)
    parser.add_argument("--cell-height", type=int, default=1024)
    parser.add_argument(
        "--padding",
        type=int,
        default=None,
        help="Transparent inset in output pixels (default: about 3%% of the shorter cell side, capped at 32 px)",
    )
    parser.add_argument(
        "--no-loop-endpoint",
        action="store_true",
        help="Do not duplicate the first frame at the end",
    )
    return parser.parse_args()


def open_frame(path: str) -> Image.Image:
    frame_path = Path(path)
    if not frame_path.is_file():
        raise ValueError(f"Frame not found: {frame_path}")

    with Image.open(frame_path) as source:
        if "A" not in source.getbands():
            raise ValueError(f"Frame has no alpha channel: {frame_path}")
        frame = source.convert("RGBA")

    alpha = frame.getchannel("A")
    if alpha.getextrema()[0] == 255:
        raise ValueError(f"Frame has no transparent pixels: {frame_path}")

    width, height = frame.size
    corners = (
        alpha.getpixel((0, 0)),
        alpha.getpixel((width - 1, 0)),
        alpha.getpixel((0, height - 1)),
        alpha.getpixel((width - 1, height - 1)),
    )
    if any(value > 1 for value in corners):
        raise ValueError(
            "Frame corners must be transparent; regenerate it with a transparent background: "
            f"{frame_path}"
        )
    for point in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        if alpha.getpixel(point) == 1:
            alpha.putpixel(point, 0)
    frame.putalpha(alpha)
    return frame


def main() -> int:
    args = parse_args()
    if min(args.columns, args.rows, args.cell_width, args.cell_height) <= 0:
        raise ValueError("Rows, columns, and cell dimensions must be positive integers.")

    padding = args.padding
    if padding is None:
        padding = max(1, min(32, min(args.cell_width, args.cell_height) // 32))
    if padding < 0 or padding * 2 >= min(args.cell_width, args.cell_height):
        raise ValueError("Padding must be non-negative and smaller than half of each cell dimension.")

    total_cells = args.columns * args.rows
    repeat_endpoint = not args.no_loop_endpoint and total_cells > 1
    required_inputs = total_cells - 1 if repeat_endpoint else total_cells
    if len(args.frames) != required_inputs:
        endpoint_note = " (the first frame will be repeated as the last)" if repeat_endpoint else ""
        raise ValueError(
            f"Grid has {total_cells} cells{endpoint_note}; expected {required_inputs} input frame(s), "
            f"got {len(args.frames)}."
        )

    frames = [open_frame(path) for path in args.frames]
    source_size = frames[0].size
    for path, frame in zip(args.frames[1:], frames[1:]):
        if frame.size != source_size:
            raise ValueError(
                f"All source frames must have the same canvas size; {path} is {frame.size}, "
                f"expected {source_size}."
            )

    if repeat_endpoint:
        frames.append(frames[0].copy())

    out_path = Path(args.output)
    if out_path.suffix.lower() != ".png":
        raise ValueError("Output must use the .png extension.")
    if out_path.exists():
        raise ValueError(f"Output already exists; choose a new filename: {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    source_width, source_height = source_size
    scale = min(
        (args.cell_width - 2 * padding) / source_width,
        (args.cell_height - 2 * padding) / source_height,
    )
    fitted_width = max(1, round(source_width * scale))
    fitted_height = max(1, round(source_height * scale))
    fitted_frames = [
        frame.resize((fitted_width, fitted_height), Image.Resampling.LANCZOS)
        for frame in frames
    ]

    sheet = Image.new(
        "RGBA",
        (args.columns * args.cell_width, args.rows * args.cell_height),
        (0, 0, 0, 0),
    )
    for index, frame in enumerate(fitted_frames):
        col = index % args.columns
        row = index // args.columns
        left = col * args.cell_width + (args.cell_width - fitted_width) // 2
        top = row * args.cell_height + (args.cell_height - fitted_height) // 2
        sheet.alpha_composite(frame, (left, top))

    sheet.save(out_path, format="PNG", optimize=True)
    print(
        f"Saved {out_path} ({sheet.width}x{sheet.height}, "
        f"{args.columns} columns x {args.rows} rows)."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(2)

