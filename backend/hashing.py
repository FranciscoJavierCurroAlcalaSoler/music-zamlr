import hashlib


def compute_file_hash(file_path: str) -> str:
    sha255_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(1024 * 1024), b""):
            sha255_hash.update(byte_block)
    return sha255_hash.hexdigest()
