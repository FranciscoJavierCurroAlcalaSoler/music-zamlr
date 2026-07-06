import os
import logging
import mutagen
from database import create_db_and_tables, database_commit, engine
from models import Track

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
            file_path=os.path.normpath(file_path),
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

ALLOWED_EXTENSIONS = {".mp3", ".flac"}  # placeholder, config file comes later
BATCH_SIZE = 100  # placeholder, config file comes later

def scan_folder(folder_path: str, engine) -> dict:
    # Known limitation: scanning the same folder twice will raise
    # sqlalchemy.exc.IntegrityError on the first duplicate file_path,
    # since file_path is unique on Track. Not handled yet: re-scan/
    # duplicate-detection is deferred, likely Phase 6 territory.
    # Deliberate scope cut for Phase 1, not an oversight.
    batch = []
    scanned_count = 0
    added_count = 0
    skipped_count = 0
    failed_count = 0
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            scanned_count += 1
            if file.lower().endswith(tuple(ALLOWED_EXTENSIONS)):
                track = read_track(os.path.join(root, file))
                if track:
                    batch.append(track)
                    added_count += 1
                else:
                    failed_count += 1
                if  len(batch) >= BATCH_SIZE:  # limit batch size to BATCH_SIZE
                    database_commit(batch, engine)
                    batch = []
            else:
                skipped_count += 1
    if batch:  # commit any remaining tracks in the batch
        database_commit(batch, engine)
    return {
        "scanned": scanned_count,
        "added": added_count,
        "skipped": skipped_count,
        "failed": failed_count
    }

FOLDER_TO_SCAN = "C:/path/to/test_music"

def main():
    create_db_and_tables()
    scan_folder(FOLDER_TO_SCAN, engine)

if __name__ == "__main__":
    main()