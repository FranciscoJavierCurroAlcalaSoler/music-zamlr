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
- Acoustic fingerprints: `fpcalc` from Chromaprint

## Requirements

- Python 3.14
- Node.js 24
- `fpcalc`, the command-line program of Chromaprint. The tool uses it to
  compare the sound of two files. Without it, the tool compares tags only and
  shows a warning.
- Both collections must be folders on the computer that runs the backend. An
  external USB drive is enough. Read
  [A collection keeps its path](#a-collection-keeps-its-path) before you use
  one.
- Audio files in the formats `.mp3`, `.flac`, or `.wav`. The scanner ignores
  all other files and counts them as **Not audio**. This includes `.m4a`,
  `.ogg`, `.opus`, and `.aiff` files.

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

4. Install `fpcalc` with the package manager of your system:

```
winget install --id AcoustID.Chromaprint --exact    # Windows
brew install chromaprint                            # macOS
sudo apt install libchromaprint-tools               # Debian and Ubuntu
```

On Windows, do not use the Chocolatey package. It installs version 1.1, which
is more than ten years old. The automated tests use the version that
`FPCALC_VERSION` names in `.github/workflows/ci.yml`.

5. Open a new terminal. Then make sure that this command shows a version:

```
fpcalc -version
```

A terminal that was open before the installation does not find `fpcalc`. For
the same reason, start the backend in a new terminal.

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
   slow one, because it reads files to compare them. The tool stores hashes and
   fingerprints in its database, so later comparisons are faster.
4. Examine the result table. Each track belongs to one group: missing, upgrade
   available, already have, needs review, or only in yours.
5. Select the tracks to import. Select a destination folder, a folder
   structure, and what must happen to a file that an upgrade replaces (see
   [What happens to a replaced file](#what-happens-to-a-replaced-file)).
6. Examine the preview. It lists every file operation before anything on disk
   changes.
7. Select **Import**. The tool writes a log file into the destination folder.

A scan and a comparison both report progress while they run. A large
collection takes minutes.

### A collection keeps its path

A collection stores the path of its root folder when you add it. You cannot
change that path later, and you cannot delete a collection. If Windows gives a
USB drive a different drive letter, the tool cannot scan that collection
again. The scan then fails with the message
`Collection path not found. It may not be mounted.` Add the drive as a new
collection, with a different name.

### What happens to a replaced file

Before an import, you select one of three actions for the files that the
upgrades replace:

- **Keep both tracks.** Your file stays where it is. The tool copies the
  better file into the destination folder as a separate file.
- **Move my track aside.** Your file moves into a folder named `_superseded`,
  directly under the destination folder. All moved files go into this one
  folder, without subfolders. If a file with the same name is already there,
  the moved file gets a numbered suffix. You can move a file back by hand.
- **Delete my track.** The tool deletes your file after it writes the better
  copy. You cannot undo this.

The scanner never reads a folder named `_superseded`, in any letter case and at
any depth in a collection. This keeps moved files out of later comparisons. It
also hides your own folder, if it has this name.

### After an import

A comparison does not know about the imported files until you scan again.
Scan the collection that contains the destination folder. Until then, a new
comparison still shows the imported tracks as missing. If the destination
folder is not in one of your collections, the tool does not show the imported
files.

### Your selection is not saved

A browser refresh clears the tracks that you selected and your answers in the
review dialog. A new comparison clears them too. Do a review and its import in
one session.

## How the tool decides that two tracks are the same

Three rules do the work. They run in this order, and each rule gets only the
tracks that the rules before it did not resolve.

**Identical file size, then identical hash.** This finds exact duplicates. It
works even when a file has no tags at all. It cannot find a better copy,
because a different encoding almost always has a different file size.

**The sound of the first two minutes.** The tool reads the first two minutes of
each file with `fpcalc` and makes an acoustic fingerprint. It compares two
fingerprints only when the durations of the two tracks are within 2 seconds of
each other. This rule finds a better copy even when the tags are wrong or
blank.

- If the sound differs, the tags cannot overrule it. The track goes to
  **missing**, and the table shows `Missing · audio differs`. The columns
  `Your format` and `Your bitrate` then show the format and bitrate of the file
  that the tool compared.
- If `fpcalc` cannot read a file, or if a file is shorter than about 12
  seconds, this rule gives no answer. The next rule then decides.
- If two of your files have the same sound, the track goes to **needs review**,
  and you decide.
- A remaster can count as a different recording. A remaster can change the
  speed or the balance of the sound, and the fingerprint then changes too. The
  tool then offers the remaster as missing. That is the safe direction: the
  result is an extra copy, not a deleted file.

The tool stores each fingerprint, so `fpcalc` reads a file only one time. If
`fpcalc` is not installed, the tool skips this rule, and a warning appears
above the result table. Without the sound, an upgrade can then be a different
recording of the song.

**Artist, title, and duration.** This rule finds a better copy when the second
rule cannot decide. Artist and title are compared without case or extra
spaces. The durations must be within 2 seconds of each other.

The third rule has two consequences that appear in the result table:

- A track with a blank artist or a blank title is never matched by the third
  rule. The second rule can still match it.
- If two or more of your tracks fall within the 2-second window, the tool does
  not choose one. The track goes to **needs review**, and you decide. An
  obvious duplicate therefore waits for you. The tool never makes an uncertain
  decision on your behalf.

**A file that cannot be read.** A comparison does not stop at a file that it
cannot read. A warning above the result table lists each such file. The tool
compares these tracks by tags only, so an upgrade among them can be a
different recording of the song. A common cause is a file that moved, or that
was deleted, after its scan. Scan the collection of that file again.

## How the tool decides that a copy is better

After the tool pairs your track with a track of theirs, it compares the two
files:

1. The format decides first. FLAC and WAV have the same rank, and both rank
   above MP3. A file with a higher rank is always better, whatever its
   bitrate.
2. If the two formats have the same rank, the higher bitrate is better. If the
   bitrates are equal, you already have the track.
3. If the tool cannot read the bitrate of one of the two files, you already
   have the track. The tool never offers to replace a file whose quality it
   did not measure.

**Known limit.** Between two lossless files, a higher bitrate does not mean
better sound. A WAV file always has a higher bitrate than a FLAC file of the
same audio, so it appears as an upgrade. A louder master compresses less, so
it can appear as an upgrade too. With **Delete my track**, the upgrade then
replaces your file. A new rule for lossless files comes next.

## Design notes

**File size comes before tags.** A human compares artist and title first. The
tool does not, because size grouping costs one lookup in memory and works on
untagged files. Hashes are computed only for files that already share a size.

**The sound is compared on your computer.** The tool does not send
fingerprints to an online service such as AcoustID. It works without a network
connection and needs no account. Your files and their fingerprints stay on your
computer.

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

## Known limits

- The action for a replaced file applies to every upgrade in one import. You
  cannot select a different action for each file.
- The tool identifies a file by its path. If you move or rename a file, the
  tool forgets its stored hash and fingerprint, and the next comparison reads
  the file again. On Windows, this also occurs when only the letter case of a
  name changes.
- The free-space warning in the preview does not count a file that moves into
  `_superseded` on a different drive. That move copies the file, so the
  destination drive can need more space than the preview shows.
- Do not scan one collection from two browser tabs at the same time. The tool
  does not prevent it, and one of the scans can fail.

## Status

The scan, the comparison, and the import all work, and the browser shows live
progress for each. The comparison uses file hashes, acoustic fingerprints, and
tags.

Three changes come next, in this order:

1. A new rule for two lossless files. Bit depth and sample rate decide, and
   bitrate does not.
2. Support for `.m4a` files. The tool reads the codec to tell ALAC, which is
   lossless, from AAC, which is lossy.
3. A setting for the order of formats.

After that, a desktop package will include `fpcalc`, and you will not install
it yourself.

## License

MIT. See [LICENSE](LICENSE).
