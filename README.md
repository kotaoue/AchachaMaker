# AchachaMaker

A video maker made by me, for me.

## Getting Started (macOS)

### Prerequisites

- Python 3.11 or later — install via [Homebrew](https://brew.sh/): `brew install python`
- ffmpeg — install via Homebrew: `brew install ffmpeg`
- (Optional) [VOICEVOX](https://voicevox.hiroshiba.jp/) desktop app running locally for voice synthesis

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

### Run Tests

```bash
python -m pytest

python main.py
```
