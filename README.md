# AchachaMaker

A video maker made by me, for me.

## Getting Started (macOS)

### Prerequisites

Install [Homebrew](https://brew.sh/) if you don't have it, then:

```bash
# Python runtime + ffmpeg
brew install python ffmpeg

# uv — fast Python package / project manager (handles virtualenvs automatically)
brew install uv
```

> (Optional) Start the [VOICEVOX](https://voicevox.hiroshiba.jp/) desktop app locally to enable voice synthesis.

### Setup

```bash
git clone https://github.com/kotaoue/AchachaMaker.git
cd AchachaMaker
uv sync          # creates .venv and installs all dependencies
```

### Run the App

```bash
uv run python main.py
```

### Run Tests

```bash
uv run pytest
```
