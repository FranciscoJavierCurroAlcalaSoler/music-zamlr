import hashlib
import logging


def compute_file_hash(file_path: str) -> str | None:
    """Return the SHA-256 of a file, or None when the filesystem refuses it.

    None, not an exception, because one unreadable file must not end a whole
    diff. The matcher then tries the tiers below for that track.

    The try covers the reads as well as the open. A read can fail after the
    open succeeds, for example when a drive disconnects in the middle of a
    file. The digest of the bytes read before that failure is a real hash of
    the wrong content. So the function returns None, never that digest.

    OSError only: a bug in this function must still raise.
    """
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(1024 * 1024), b""):
                sha256_hash.update(byte_block)
    except OSError as error:
        logging.warning("Error computing hash for %s: %s", file_path, error)
        return None
    return sha256_hash.hexdigest()
