# AchachaMaker

A video maker made by me, for me.

## Getting Started (macOS)

### Prerequisites

- Python 3.11 or later — install via [Homebrew](https://brew.sh/): `brew install python`
- ffmpeg — install via Homebrew: `brew install ffmpeg`
- (Optional) [VOICEVOX](https://voicevox.hiroshiba.jp/) desktop app running locally for voice synthesis

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/kotaoue/AchachaMaker.git
cd AchachaMaker

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Run the app
python main.py
```

### Run Tests

```bash
python -m pytest
```
