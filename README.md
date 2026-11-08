# Score Player

A macOS app for reading sheet-music and guitar-tab PDFs, playing the recognized notes, and exporting MIDI.

Open **Start Score Player.command**, then use the + button to upload a PDF. The local address is http://127.0.0.1:8767.

Auto detects standard notation or six-string guitar tablature. You can also select the format yourself. Use ▶ to play, ■ to stop, ↻ to loop, and ↓ MIDI to export. Pitch names, starting beats, and note lengths are editable. A beat is one quarter note. Transpose is measured in semitones. The PDF tab shows the source document. The ⓘ control contains recognition limitations.

## What it supports

- Printed notation PDFs, including scans, through Audiveris 5.11.0.
- Six-line guitar tab with fret numbers, including image-only PDFs, using local PDF analysis and Apple Vision OCR.
- MusicXML and compressed MusicXML imports.
- Synthesized playback, tempo, transpose, part selection, and Standard MIDI File downloads.
- Standard guitar, Drop D, and DADGAD tuning. Select Tab to expose tuning and spacing controls.

## Limits

Recognition requires review. Tab imports now read printed rhythm by default when the layout uses separate stems beneath six string lines. The reader recognizes quarter, half, and beamed notes, single flags, dots, common rests, multi-measure rests, and tied continuations. Measures must add up to the chosen meter. Unreadable measures or frets stop the import with a review message. For tabs without readable rhythm markings, select Tab → Rhythm → Even for explicitly approximate timing. Bends, slides, hammer-ons, capo markings, repeat signs, and other guitar techniques are not interpreted. Staff notation depends on Audiveris recognition quality. Broken rhythm exports are rejected. Repeats are expanded when possible, and tied notes are combined. Playback uses one tempo and one selected sound. Printed numeric tempo markings are read when available. Tempo changes and tuplets are not supported by the tab rhythm reader. The Meter setting defaults to 4/4 and can be changed under Tab. Silent bars and trailing rests are preserved in playback and MIDI exports. Unpitched percussion, handwriting, and formats other than six-string guitar tab are not supported. Playable parts can be selected individually. MIDI export includes the selected parts with a single instrument program.

Files are limited to 30 MB and PDFs to 20 pages. Scans should be straight, clear, and normally sized. Narrow columns, cropped string lines, unusual layouts, and distorted scans can fail. Failure on a page is reported in recognition notes. This is an initial implementation, not a guarantee of accurate transcription for arbitrary scores.

## Library

Uploaded PDFs are saved automatically. Open **Library** to reopen them or use ↓ to download an original. Press 💾 to save the current note edits, tempo, sound, transpose, and loop selection. Saved scores reopen without running recognition again.

The library database, PDFs, recognition results, and logs live in `data/`. Back up that whole folder to preserve the library. Browser storage also restores the most recent session. The GitHub repository excludes all uploaded PDFs and saved scores.

The server listens on localhost port 8767. Recognition can take up to 15 minutes, and imports run one at a time. Closing the browser does not stop the server.

## Install

Requires macOS, Python 3.9–3.12, and Apple's command-line developer tools (`xcode-select --install`). The app was tested on Apple Silicon with Python 3.9. Run `Setup.command` to create the Python environment and compile the included Apple Vision helpers. Then open `Start Score Player.command`.

For staff notation, download [Audiveris 5.11.0](https://github.com/Audiveris/audiveris/releases/tag/5.11.0) for your Mac and place `Audiveris.app` inside `engines/`. Open Audiveris once to complete its setup and install English OCR data. Guitar tab and MusicXML work without Audiveris. Third-party applications and models are not included in this repository.

Re-run setup after moving the project, since Python virtual environments are not portable.

## Checks

```sh
.venv/bin/python -m pytest tests -q
node tests/test_loop.cjs
node --check static/app.js
```

The PDF fixtures used by the tests are generated locally. The scanned-tab test requires the compiled Apple Vision helper.

## Sources and third-party software

- [Audiveris 5.11.0](https://github.com/Audiveris/audiveris/releases/tag/5.11.0), AGPL-3.0. Source: https://github.com/Audiveris/audiveris/tree/5.11.0. Installed separately, without modification.
- [Audiveris CLI documentation](https://github.com/Audiveris/audiveris/wiki/CLI-Arguments).
- [Tesseract English model](https://github.com/tesseract-ocr/tessdata_fast), Apache-2.0.
- [music21](https://github.com/cuthbertLab/music21), BSD-3-Clause.
- [PyMuPDF](https://github.com/pymupdf/PyMuPDF), AGPL/commercial licensing. Review applicable licensing before redistribution.
- Apple Vision runs locally through the small Objective-C helper whose source is included.

The repository contains the application source. Run it locally on a Mac. GitHub does not host the recognition server.

Use ⟳ to reread the currently loaded PDF with the new rhythm reader. Existing saved edits remain until the new import succeeds.

## Section looping

Drag the two handles below the piano roll to choose a section. Moving a handle enables ↻ and highlights that range. Playback repeats between those boundaries, including sustained notes that begin before the selection. Handles snap to quarter-beat increments, support keyboard arrows, and cannot cross. Changing the range during playback resumes when the handle is released. The range is saved with the current browser session and with 💾 in the Library. Turning ↻ off restores normal full-score playback. MIDI download still exports the full selected part.
