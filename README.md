# PyToExe

Tkinter GUI that wraps [PyInstaller](https://pyinstaller.org/) to package Python scripts into standalone Windows executables, with icon assignment and common build options.

## Features

- Script picker (`.py`)
- Icon picker — accepts `.ico`, `.png`, `.jpg`, `.bmp` (auto-converts to `.ico` via Pillow)
- Custom app name and output directory
- One-file or one-directory build
- Console or windowed (no console) mode
- Clean build / UPX compression toggles
- Hidden imports (comma-separated)
- Additional data files/folders (`--add-data`)
- Free-form extra PyInstaller CLI arguments
- Threaded build with live log output and cancel support
- Save/load build presets as JSON (`.p2e.json`)
- Auto-detects and offers to install PyInstaller if missing

## Requirements

- Windows
- Python 3.9+
- [PyInstaller](https://pyinstaller.org/), [Pillow](https://python-pillow.org/) (see `requirements.txt`)

## Setup

```bash
pip install -r requirements.txt
```

## Usage

Run the GUI directly:

```bash
python app.py
```

1. Browse to the target `.py` script.
2. (Optional) Select an icon image.
3. Set app name, output directory, and options.
4. Click **Build EXE**.
5. Find the built executable in the chosen output directory.

## Building PyToExe itself into an .exe

```bash
build_exe.bat
```

Produces `dist\PyToExe.exe` (onefile, windowed).

## Project Structure

```
app.py            GUI application
requirements.txt  Python dependencies
build_exe.bat      Packages app.py into PyToExe.exe
```

## License

MIT
