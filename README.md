# Typing Tutor

A TUI-based typing tutor designed for targeted practice using bigram-weighted lesson generation.

## Features

- **TUI Interface**: Terminal-based interface using `curses` with real-time feedback (color-coded accuracy).
- **Targeted Practice**: Automatically identifies bigrams where you make mistakes and prioritizes them in future lessons using weighted sampling.
- **Progress Tracking**: Records mistakes and lesson history in SQLite databases to improve practice efficiency over time.
- **Word Expiry**: Prevents recently typed words from appearing too frequently.
- **Live Stats**: Displays real-time Characters Per Second (CPS) and Accuracy during lessons.

## Installation

This project uses `uv` for dependency management.

```bash
# Install dependencies
uv sync
```

## Usage

To start a typing session:

```bash
uv run tutor.py
```

### Controls

- **Keys**: Type the text as displayed.
- **Backspace**: Correct mistakes in the current word.
- **Ctrl-C**: Skip to the next lesson.
- **ESC**: Exit the application.

## Project Structure

- `tutor.py`: Main application entry point and TUI logic.
- `stats.db`: SQLite database storing mistake history and session data.
- `dictionaries/`: Contains the word databases used for lesson generation.
- `scripts/`: Utilities for processing dictionaries and generating indexes.

## Requirements

- Python 3.13+
- `curses` (included in most Unix-like Python distributions)
