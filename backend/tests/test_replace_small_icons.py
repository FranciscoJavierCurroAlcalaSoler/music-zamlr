import struct
import sys
import zlib

import pytest

import replace_small_icons
from replace_small_icons import ICO_ENTRY, ICO_HEADER, replace_images


def _png(size, marker):
    # A PNG with a real signature and IHDR, which is all the code reads. The
    # marker makes two PNGs of one size tell apart.
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    chunk = b"IHDR" + ihdr
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", len(ihdr))
        + chunk
        + struct.pack(">I", zlib.crc32(chunk))
        + marker
    )


def _ico(images):
    # The layout `tauri icon` writes: header, directory, then each PNG.
    directory = b""
    data = b""
    offset = ICO_HEADER.size + ICO_ENTRY.size * len(images)
    for size, png in images:
        side = 0 if size == 256 else size
        directory += ICO_ENTRY.pack(side, side, 0, 0, 1, 32, len(png), offset)
        data += png
        offset += len(png)
    return ICO_HEADER.pack(0, 1, len(images)) + directory + data


def _images(ico):
    _, _, count = ICO_HEADER.unpack_from(ico, 0)
    images = {}
    for index in range(count):
        width, *_, size, offset = ICO_ENTRY.unpack_from(
            ico, ICO_HEADER.size + ICO_ENTRY.size * index
        )
        images[width or 256] = ico[offset : offset + size]
    return images


ORIGINAL = {size: _png(size, b"old") for size in (16, 24, 32, 256)}


def test_the_given_sizes_are_replaced_and_the_rest_kept():
    # The new 16 px image is longer than the old one, so every image after
    # it moves: a stale offset would read the wrong bytes for all of them.
    new = {16: _png(16, b"new and longer"), 24: _png(24, b"new")}

    result = _images(replace_images(_ico(list(ORIGINAL.items())), new))

    assert result == {16: new[16], 24: new[24], 32: ORIGINAL[32], 256: ORIGINAL[256]}


def test_the_256_px_image_is_found_through_its_zero():
    # The directory stores 256 as 0, because a byte cannot hold it.
    new = {256: _png(256, b"new")}

    result = _images(replace_images(_ico(list(ORIGINAL.items())), new))

    assert result[256] == new[256]


def test_main_replaces_the_32_px_window_icon(tmp_path, monkeypatch):
    # The window's title bar and taskbar icon come from the 32 px image, so
    # a run that left it out would change nothing the user looks at.
    ico_path = tmp_path / "icon.ico"
    ico_path.write_bytes(_ico(list(ORIGINAL.items())))
    monkeypatch.setattr(replace_small_icons, "ICO_PATH", ico_path)
    png_dir = tmp_path / "small"
    png_dir.mkdir()
    for size in (16, 24, 32):
        (png_dir / f"{size}x{size}.png").write_bytes(_png(size, b"new"))
    monkeypatch.setattr(sys, "argv", ["replace_small_icons.py", str(png_dir)])

    replace_small_icons.main()

    result = _images(ico_path.read_bytes())
    assert result[32] == _png(32, b"new")
    assert result[256] == ORIGINAL[256]


def test_a_size_the_icon_lacks_is_refused():
    ico = _ico([(32, ORIGINAL[32])])

    with pytest.raises(ValueError, match="no 16 px image"):
        replace_images(ico, {16: _png(16, b"new")})


def test_a_png_of_the_wrong_size_is_refused():
    ico = _ico(list(ORIGINAL.items()))

    with pytest.raises(ValueError, match="16 px image is not 16 px"):
        replace_images(ico, {16: _png(24, b"new")})


def test_a_file_that_is_not_an_icon_is_refused():
    # Type 2 is a cursor file, which has the same layout.
    cursor = ICO_HEADER.pack(0, 2, 0)

    with pytest.raises(ValueError, match="Not an icon file"):
        replace_images(cursor, {})


def test_a_file_that_is_not_a_png_is_refused():
    ico = _ico(list(ORIGINAL.items()))

    with pytest.raises(ValueError, match="Not a PNG file"):
        replace_images(ico, {16: b"BM not a png"})
