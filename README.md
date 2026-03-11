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

## Intended Future Features

- **More Customizability in terms of metrics being displayed and overall aesthetic appearance**
- **Smoother animations**
- **Better pattern recognition accuracy**
- **More skillset coverage (reading, finger control, consistency, etc)**
- **Better performance on lower end PCs**
