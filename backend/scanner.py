import os
import sys
import logging
import hashlib
import mutagen
from datetime import datetime
from database import create_db_and_tables, database_commit, create_collection, engine
from models import Collection, Track

logging.basicConfig(level=logging.INFO)

def compute_file_hash(file_path: str) -> str:
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_tag(audio, keys: list[str]) -> str | None:
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
    
def read_track(file_path: str, collection_id: int) -> Track | None:
    try:
        audio = mutagen.File(file_path, easy=True)
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
            file_hash=compute_file_hash(file_path),
            collection_id=collection_id)
    except Exception as e:
        logging.error(f"Failed to read track information from {file_path}: {e}")
        return None

ALLOWED_EXTENSIONS = {".mp3", ".flac"}  # placeholder, config file comes later
BATCH_SIZE = 100  # placeholder, config file comes later

def scan_folder(folder_path: str, collection_id: int, engine) -> dict:
    # Known limitation: scanning the same folder twice will raise
    # sqlalchemy.exc.IntegrityError on the first file whose path already
    # exists *within that same collection*, since (collection_id, file_path)
    # is a composite unique constraint on Track. Two different collections
    # can safely share a path (e.g. same drive letter reused for different
    # external drives). Not handled yet: re-scan/duplicate-detection is
    # deferred, likely Phase 6 territory. Deliberate scope cut, not an
    # oversight.
    batch = []
    scanned_count = 0
    added_count = 0
    skipped_count = 0
    failed_count = 0
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            scanned_count += 1
            if file.lower().endswith(tuple(ALLOWED_EXTENSIONS)):
                track = read_track(os.path.join(root, file), collection_id=collection_id)
                if track:
                    batch.append(track)
                    added_count += 1
                else:
                    failed_count += 1
                if  len(batch) >= BATCH_SIZE:
                    database_commit(batch, engine)
                    batch = []
            else:
                skipped_count += 1
    if batch:
        database_commit(batch, engine)
    return {
        "scanned": scanned_count,
        "added": added_count,
        "skipped": skipped_count,
        "failed": failed_count
    }

def main():
    if len(sys.argv) < 3:
        print("Usage: python scanner.py <folder_to_scan> <collection_name>")
        sys.exit(1)
    
    folder_to_scan = sys.argv[1]
    collection_name = sys.argv[2]
    create_db_and_tables()

    collection = create_collection(
        Collection(
            name=collection_name,
            root_path=os.path.normpath(folder_to_scan),
            last_scanned_at=datetime.now().isoformat()
        ),
        engine
    )
    result = scan_folder(folder_to_scan, collection.id, engine)
    print(result)

if __name__ == "__main__":
    main()