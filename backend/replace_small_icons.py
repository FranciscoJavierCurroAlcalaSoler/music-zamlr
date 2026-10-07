"""Put the small artwork into the 16, 24 and 32 px images of the app's .ico.

At 16 px the full icon's Z is about three pixels tall, so the three
smallest images come from a simpler drawing,
frontend/src-tauri/app-icon-small.svg. `tauri icon` makes every image of
the .ico from one drawing, so it cannot do this, and running it again puts
the unreadable images back. Run this after it.

Usage, from frontend/:

    npm run tauri icon src-tauri/app-icon-small.svg -- -p 16,24,32 -o <dir>
    python ../backend/replace_small_icons.py <dir>

The .ico that `tauri icon` writes holds each image as a PNG, so replacing
one is a matter of bytes: no image library is needed.
"""

import struct
import sys
from collections.abc import Mapping
from pathlib import Path

ICO_PATH = Path(__file__).resolve().parent.parent / "frontend/src-tauri/icons/icon.ico"
# 32 is the one that matters most. On Windows, Tauri sets the window icon
# from the exe's image at the system's large icon size, 32 px at 100 %
# scale, and Windows shrinks that image for the title bar and shows it on
# the taskbar. Windows takes the 16 and 24 px images where it reads the
# file itself at those sizes.
SMALL_SIZES = (16, 24, 32)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ICO_HEADER = struct.Struct("<HHH")
ICO_ENTRY = struct.Struct("<BBBBHHII")


def png_size(png: bytes) -> tuple[int, int]:
    """Width and height from a PNG's IHDR chunk, which always comes first."""
    if not png.startswith(PNG_SIGNATURE):
        raise ValueError("Not a PNG file")
    return struct.unpack_from(">II", png, 16)


def replace_images(ico: bytes, pngs: Mapping[int, bytes]) -> bytes:
    """A copy of ico with the image of each given size replaced.

    A size the .ico does not have raises instead of being skipped, and so
    does a PNG whose own size differs from its slot. Either one would
    otherwise leave the unreadable image in place with nothing to say so.
    """
    _, kind, count = ICO_HEADER.unpack_from(ico, 0)
    if kind != 1:
        raise ValueError("Not an icon file")

    entries = []
    for index in range(count):
        *header, size, offset = ICO_ENTRY.unpack_from(
            ico, ICO_HEADER.size + ICO_ENTRY.size * index
        )
        # The six fields before size and offset are kept as they are.
        entries.append([*header, ico[offset : offset + size]])

    # In the directory, 0 means 256: one byte cannot hold it.
    by_size = {(entry[0] or 256): entry for entry in entries}
    for size, png in pngs.items():
        if size not in by_size:
            raise ValueError(f"The icon has no {size} px image")
        if png_size(png) != (size, size):
            raise ValueError(f"The PNG for the {size} px image is not {size} px")
        by_size[size][6] = png

    # Offsets are written again, because a new image has its own length and
    # every image after it moves.
    directory = b""
    images = b""
    offset = ICO_HEADER.size + ICO_ENTRY.size * len(entries)
    for width, height, colours, reserved, planes, bits, data in entries:
        directory += ICO_ENTRY.pack(
            width, height, colours, reserved, planes, bits, len(data), offset
        )
        images += data
        offset += len(data)
    return ICO_HEADER.pack(0, 1, len(entries)) + directory + images


def main() -> None:
    png_dir = Path(sys.argv[1])
    pngs = {size: (png_dir / f"{size}x{size}.png").read_bytes() for size in SMALL_SIZES}
    ICO_PATH.write_bytes(replace_images(ICO_PATH.read_bytes(), pngs))


if __name__ == "__main__":
    main()
