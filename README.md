# Music Zamlr

Music Zamlr compares two local music collections. It shows which tracks you do
not have, which tracks exist in better quality in the other collection, and
which tracks you already have. Then it copies only the files you select.

The tool exists for one situation. A friend carries a music collection on an
external drive. You have an old copy of it. You want the tracks you never
received, and the tracks where the friend's copy is better than yours.

## How it works

The backend runs on your own computer. A browser cannot read a local drive,
and a remote server cannot reach one. The FastAPI backend therefore reads your
drives directly with normal file operations. The React interface talks to it at
`localhost`.

- Backend: FastAPI, SQLModel, SQLite
- Frontend: React, TypeScript, MUI, Vite

## Requirements

- Python 3.14
- Node.js 24
- Both collections must be folders on the computer that runs the backend. An
  external USB drive is enough.

## Install

1. Clone the repository.
2. Install the backend dependencies:

```
cd backend
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

3. Install the frontend dependencies:

```
cd frontend
npm install
```

## Run

Open two terminals. Start the backend in the first one:

```
cd backend
fastapi dev main.py
```

Start the frontend in the second one:

```
cd frontend
npm run dev
```

Then open `http://localhost:5173` in a browser. The backend answers on port
8000. The frontend expects it there.

## Use

1. Add a collection. Give it a name and the path to its root folder. The
   scanner reads every audio file and stores the tags and the technical data.
2. Add the second collection in the same way.
3. Select both collections and start a comparison. The first comparison is the
   slow one, because it reads whole files to compare them.
4. Examine the result table. Each track belongs to one group: missing, upgrade
   available, already have, needs review, or only in yours.
5. Select the tracks to import. Select a destination folder, a folder
   structure, and what must happen to a file that an upgrade replaces.
6. Examine the preview. It lists every file operation before anything on disk
   changes.
7. Select **Import**. The tool writes a log file into the destination folder.

A scan and a comparison both report progress while they run. A large
collection takes minutes.

## How the tool decides that two tracks are the same

Two rules do the work.

**Identical file size, then identical hash.** This finds exact duplicates. It
works even when a file has no tags at all. It cannot find a better copy,
because a different encoding almost always has a different file size.

**Artist, title, and duration.** This is the only rule that finds a better
copy, so it runs on the tracks the first rule did not resolve. Artist and
title are compared without case or extra spaces. The durations must be within
2 seconds of each other.

The second rule has two consequences that appear in the result table:

- A track with a blank artist or a blank title is never matched by the second
  rule.
- If two or more of your tracks fall within the 2-second window, the tool does
  not choose one. The track goes to **needs review**, and you decide. An
  obvious duplicate therefore waits for you. The tool never makes an uncertain
  decision on your behalf.

## Design notes

**File size comes before tags.** A human compares artist and title first. The
tool does not, because size grouping costs one lookup in memory and works on
untagged files. Hashes are computed only for files that already share a size.

**The server computes the comparison again at import time.** The request names
the tracks to import, not what they are. A bug in the table can therefore
select the wrong row, but it cannot delete the wrong file. The server holds
its own answer and compares the request against it.

**Progress arrives over Server-Sent Events.** A scan, a comparison, and an
import each stream their progress to the browser and end with one result. A
job registry can survive a lost connection, but it also needs a job table,
identifier generation, and an expiry policy. Nothing else here needs those.

**Nothing is overwritten in silence.** Two files with the same destination
name get a numbered suffix, in the way Windows Explorer does it. A file is
deleted only after its replacement is written. An uncertain match goes to you.

**The preview warns before an import that cannot fit.** It compares the total
size of the files to copy against the free space on the destination drive. It
warns and lets you continue, because you can clear space before you confirm.

## Status

The scan, the comparison, and the import all work, and the browser shows live
progress for each. Acoustic fingerprints are the next piece of work. They will
identify the same recording across different encodings, which the current
rules can miss.

## License

MIT. See [LICENSE](LICENSE).
