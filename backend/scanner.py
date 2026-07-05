from models import Track
import mutagen
import os
import logging

logging.basicConfig(level=logging.INFO)

def compute_file_hash(file_path: str) -> str:
    # Implementation for computing file hash (e.g., SHA256)
    import hashlib
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read and update hash string value in blocks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_tag(audio, keys: list[str]) -> str | None:
    # try each key in order, return the first non-empty value found
    for key in keys:
        value = audio.get(key, [None])[0]
        if value is not None and value != '':
            return value
    return None

def year_from_date(date_str: str | None) -> int | None:
    try:
        # Assuming the date is in the format 'YYYY-MM-DD' or 'YYYY'
        return int(date_str.split('-')[0])
    except (ValueError, AttributeError):
        return None

def track_number_from_tag(track_number_str: str | None) -> int | None:
    try:
        # Assuming the track number is in the format 'X/Y' or 'X'
        return int(track_number_str.split('/')[0])
    except (ValueError, AttributeError):
        return None
    
def read_track(file_path: str) -> Track | None:
    try:
        # Implementation for reading track information
        audio = mutagen.File(file_path, easy=True)
        # Extract relevant information from the audio file
        # This is a simplified example - you would need to handle different audio formats appropriately
        return Track(
            file_path=file_path,
            file_name=os.path.basename(file_path),
            bit_rate=audio.info.bitrate,
            sample_rate=audio.info.sample_rate,
            duration=round(audio.info.length),
            title=get_tag(audio, ['title']),
            artist=get_tag(audio, ['artist']),
            album=get_tag(audio, ['album']),
            track_number=track_number_from_tag(get_tag(audio, ['tracknumber'])),
            year=year_from_date(get_tag(audio, ['date', 'year'])),
            format=os.path.splitext(file_path)[1].upper().strip('.'),
            bit_depth=audio.info.bits_per_sample if hasattr(audio.info, 'bits_per_sample') else None,
            file_size=os.path.getsize(file_path),
            file_hash=compute_file_hash(file_path))
    except Exception as e:
        logging.error(f"Failed to read track information from {file_path}: {e}")
        return None