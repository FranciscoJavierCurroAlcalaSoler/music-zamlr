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
- Audio files in the formats `.mp3`, `.flac`, `.wav`, `.aif` or `.aiff`,
  `.aac`, `.opus`, `.tta`, `.ape`, `.tak`, `.ofr`, `.mpc`, `.wv`, `.wma`,
  `.dsf`, `.dff`, `.m4a`, or `.ogg`. An `.m4a` file must hold ALAC or AAC
  audio, and an `.ogg` file must hold Vorbis, Opus, or FLAC audio. A `.wv`
  file must not hold DSD audio, and a `.wma` file must not hold WMA Pro over
  S/PDIF. The scanner lists a file with other audio inside as a file that it
  cannot read. The scanner ignores all other files and counts them as **Not
  audio**.

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

If you are not sure that every upgrade is correct, select **Move my track
aside**. It keeps your file, and you can move the file back.

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

1. The format decides first. The lossless formats (FLAC, ALAC, WAV, AIFF, TTA,
   Monkey's Audio, TAK, OptimFROG, WavPack, and WMA Lossless) and DSD have
   the same rank. The lossy formats (MP3, AAC, Opus, Vorbis, Musepack, WavPack hybrid,
   and WMA) have a lower rank. A file with a higher rank is always better,
   whatever its bitrate. You can change this order. See
   [The order of the formats](#the-order-of-the-formats).
2. If both files are lossless, bit depth and sample rate decide.
   Their file is better only if neither value is lower than yours and at least
   one value is higher. Bitrate does not count here. A lossless bitrate shows
   how well the sound compresses, not how good the sound is.
3. If one file is DSD and the other file is lossless, neither file is better.
   DSD records sound in a different way, so the numbers of the two files do
   not compare. If both files are DSD, the higher sample rate is better.
4. If both files are lossy, the higher bitrate is better.
5. If the two files are equal, you already have the track. If the tool cannot
   read a value that it needs from one of the files, you already have the
   track too. The tool never offers to replace a file whose quality it did not
   measure.

Every upgrade in the table is a file that **Delete my track** removes from your
collection. The rule can be wrong about a track, for example about a file that
was converted to a higher sample rate. The deletion is then permanent.

The rule for lossless files has three consequences:

- A remaster in the same format, bit depth, and sample rate is not offered as
  an upgrade, even if it sounds different.
- If each file is better on a different value, neither file is an upgrade.
  For example, a 24-bit file at 44.1 kHz and a 16-bit file at 96 kHz are not
  upgrades of each other.
- **Known limit.** The rule reads the numbers in the file, not the sound. A
  44.1 kHz recording that was converted to 96 kHz still counts as an upgrade.
  So does a 32-bit float WAV file from an audio editor.

### The order of the formats

The **Settings** tab holds the order of the formats. The tool starts with the
order in rule 1 above, and you can change it.

The formats are in tiers. All the formats in one tier are equally good. A file
in a higher tier is better than a file in a lower tier, whatever its bitrate.
Two files in the same tier go to rules 2 to 5 above.

Each format has two buttons: **↑** moves it to the tier above, **↓** to the
tier below. A format that is alone in the top or the bottom tier does not
move. A format that shares a tier moves out of it into a new tier of its own.
Each tier has its own buttons, **↑ Move tier** and **↓ Move tier**, which move
the whole tier with all its formats.

Select **Save** to store the order. The tool uses the stored order for every
comparison, and also for the comparison that it makes again during an import.
Select **Reset** to go back to the order in rule 1.

Three rules apply to every order:

- **A lossy format and a lossless format are never in the same tier.** A
  bitrate means something different for the two, so the tool blocks the move
  and shows a message. Use **↑ Move tier** to change the position of a whole
  tier.
- **A DSD format can be in a tier with lossless formats.** Rule 3 above still
  applies: a DSD file and a lossless file are never upgrades of each other.
- **A format that a later version of the tool adds** goes into the lowest tier
  of its own kind. A lossless format goes into the lowest lossless tier, and a
  lossy format into the lowest lossy tier. The tab then lists the names of
  these formats. Move them if you want them in a different tier.

A comparison on the screen shows the result of the order that was stored when
it ran. If you store a different order after that, the comparison says that it
is out of date. Select **Compare** again to get current results.

> **Warning.** You can put a lossy tier above a lossless tier. The tool then
> offers a lossy file as an upgrade of a lossless file. With **Delete my
> track**, the import deletes your lossless file. The Settings tab shows a
> warning while the order has a lossy tier above a lossless tier.

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

**The preview warns before an import that cannot fit.** It compares the free
space on the destination drive against the total size of the files to copy,
plus every file that moves into `_superseded` from a different drive. Such a
move copies the file, so the destination drive holds both your old file and
the better one. The tool warns and lets you continue, because you can clear
space before you confirm.

## Known limits

- The action for a replaced file applies to every upgrade in one import. You
  cannot select a different action for each file.
- The tool identifies a file by its path. If you move or rename a file, the
  tool forgets its stored hash and fingerprint, and the next comparison reads
  the file again. On Windows, this also occurs when only the letter case of a
  name changes.
- The free-space warning in the preview reads the drive letter of a path, not
  the volume behind it. If your destination folder is a mount point for
  another disk, the warning can count a move into `_superseded` as free when
  it is not.
- Do not scan one collection from two browser tabs at the same time. The tool
  does not prevent it, and one of the scans can fail.
- A TrueAudio (`.tta`) file reports no bit depth. The tool then cannot compare
  two TTA files of one recording, so you already have the track. The result
  table shows no bitrate for a TTA file.
- The result table shows no bitrate for a Monkey's Audio (`.ape`), TAK,
  OptimFROG (`.ofr`), or WavPack (`.wv`) file. These files report no bitrate. The comparison does not need it, because bit
  depth and sample rate decide between two lossless files.
- `fpcalc` cannot read an OptimFROG file. The tool compares an OptimFROG track
  by artist, title, and duration only. An upgrade to or from an OptimFROG file
  can therefore be a different recording of the song.
- A WavPack hybrid file counts as lossy, even when its correction file
  (`.wvc`) is beside it. The import copies only the `.wv` file, and `fpcalc`
  reads only that file. A hybrid file reports no bitrate, so the tool cannot
  compare two hybrid files of one recording. You then already have the track.
- A WMA Lossless file reports no bit depth. The tool then cannot compare it
  with another lossless file of one recording, so you already have the track.
- `fpcalc` cannot read a DSDIFF (`.dff`) file. The tool compares a DSDIFF track
  by artist, title, and duration only. An upgrade between two DSDIFF files can
  therefore be a different recording of the song.

## Status

The scan, the comparison, and the import all work, and the browser shows live
progress for each. The comparison uses file hashes, acoustic fingerprints, and
tags. The **Settings** tab holds the order of the formats.

A desktop package will come next. It will include `fpcalc`, and you will not
install it yourself.

## License

MIT. See [LICENSE](LICENSE).
