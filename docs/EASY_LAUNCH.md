# Easy Launch

NEPSE Quant Terminal can be launched without manually creating a virtual environment.

## macOS

Double-click:

- `Nepse Quant Terminal.app`, or
- `Launch Quant Terminal.command`

The launcher creates `.venv` if needed, installs `requirements.txt`, downloads the bundled market database if missing, runs preflight, then opens the desktop GUI. The macOS app bundle launches it without opening a Terminal window; the `.command` script itself still runs in Terminal.

Keep `Nepse Quant Terminal.app` inside the repo folder. It is a lightweight launcher that uses the files beside it; do not drag it into `/Applications` by itself.

If macOS blocks the app because it was downloaded from the internet:

1. Right-click `Nepse Quant Terminal.app`
2. Click **Open**
3. Confirm **Open**

Python 3.12 is recommended. Python 3.10 through 3.13 is supported.

## Windows

Double-click:

- `Launch Quant Terminal.bat`

The launcher creates `.venv`, installs dependencies, downloads the bundled market database if missing, runs preflight, then opens the desktop GUI. Install the Tk package that matches your Python if the launcher reports that Tkinter is unavailable (for example, `python3-tk` on Debian or Ubuntu).

Python 3.12 is recommended. During Python install, select **Add python.exe to PATH**.

## Linux

From the repository folder, run:

```bash
"./Launch Quant Terminal.sh"
```

The script prefers a supported `.venv` already in this checkout, then finds Python 3.10–3.13 on `PATH` and delegates setup to the normal bootstrap. Python 3.12 and Tk (`python3-tk` on Debian or Ubuntu) are recommended. If `.venv` exists with an unsupported Python, the launcher keeps it and uses a separate `.venv-linux` environment. The prebuilt database still comes from the existing `nlethetech/nepse-quant-terminal` v3.0 release; changing the Git remote does not move that data asset.

To add this checkout to your desktop application menu, run:

```bash
"./Launch Quant Terminal.sh" --install-desktop
```

This installs or updates `nepse-quant-terminal.desktop` under `$XDG_DATA_HOME/applications`, or `~/.local/share/applications` when `XDG_DATA_HOME` is unset or relative. The entry uses the checkout's absolute path. Run the installer again if you move the repository.

## What Gets Created

The launcher writes only local runtime files:

- `.venv/`
- `.venv-linux/` if the existing `.venv` uses an unsupported Python version
- `data/nepse_market_data.db` if missing
- `data/runtime/`

These are local machine files and should not be committed.

## Troubleshooting

- If dependency installation fails, install Git and launch again. The NEPSE package is installed from GitHub.
- If the dashboard opens but data is stale, run `python setup_data.py --scrape --days 90` from the activated environment or use the normal scraper workflow.
- If setup fails, run the `.command` or `.bat` launcher directly so its error remains visible.
- To use the optional Textual interface, run `python scripts/launch/bootstrap.py --tui` from the repository folder.
