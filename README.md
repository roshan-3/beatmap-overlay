# I still don't have a name for this yet so it's just gna be called beatmap overlay for now

A real-time osu! beatmap analysis overlay. Hooks into the osu! process to detect your selected map and displays key stats: BPM, note density, jump distance, stream info alongside a difficulty graph that plots section-by-section star ratings coloured by pattern type (streams, jumps, tech), using rosu-pp for difficulty calculation.

## Requirements

- Windows
- osu! (stable)

## Installation

### Executable (recommended)

Download the latest `beat-overlay.exe` from [Releases](https://github.com/roshan-3/beatmap-overlay/releases).

### From source

Requires Python 3.10+

```bash
git clone https://github.com/roshan-3/beatmap-overlay.git
cd beatmap-overlay
pip install -r requirements.txt
```

## Usage

### Overlay

Launch osu!, then run:

```bash
python overlay/main.py
```

The overlay appears in the top-right corner of your screen.
- **Drag** to reposition
- **Right-click** to close

### CLI

Extract features from a single map or a folder of maps:

```bash
python classify.py map.osu
python classify.py maps/
python classify.py maps/ --out results.json --pretty
```

## Known Limitations

- **Pattern classification accuracy**: Stream, jump, and tech labels are based on note-level heuristics (stream gap, jump distance, direction change frequency). They give a reasonable approximation but won't always match how a map actually feels to play. Classification accuracy needs heavy improvement but lots of feedback is necessary.

- **Skillset coverage**: The overlay currently represents aim and speed (streams/jumps/tech). Skillsets like reading, finger control, and consistency are not measured.

- **Difficulty switching**: If the overlay doesn't update when switching between difficulties of the same song, run the following in an admin terminal and restart your PC:
  ```
  fsutil behavior set disablelastaccess 0
  ```
  This re-enables file access time tracking, which the overlay uses to detect which difficulty is selected.
