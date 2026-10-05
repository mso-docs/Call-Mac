# Your first time using Call Mac

Call Mac opens in your web browser and helps with technology questions, one step
at a time. Ollama is the separate app that runs its AI. Both need to be running.
This guide installs them on the same computer, so no server address is needed.

You will copy a few commands. A **terminal** is a window where you type commands;
copy one line at a time and press **Enter**. Wait until each finishes before
entering the next. Do not copy the ``` marks around examples.

## 1. Download Call Mac

On the [Call Mac repository page](https://github.com/mso-docs/Call-Mac), click
**Code → Download ZIP**. Find the ZIP in Downloads and extract it (Windows:
right-click → **Extract All**; macOS: double-click). Move the extracted folder
somewhere you can find again, such as Documents. Keep all its files together.
You do not need Git or a GitHub account.

## 2. Install Python and Ollama

Python runs Call Mac. Ollama runs the AI.

- **Windows:** Install Python 3.11 or newer from
  [Python's Windows downloads](https://www.python.org/downloads/windows/).
  Follow the installer's instructions; if offered **Add Python to PATH**, enable it.
  Install [Ollama for Windows](https://ollama.com/download/windows), then open it
  from Start. Open a new terminal after installing.
- **macOS:** Install Python 3.11 or newer from
  [Python's macOS downloads](https://www.python.org/downloads/macos/).
  Download [Ollama for macOS](https://ollama.com/download/mac), install it in
  Applications, and open it. Complete any prompts to make the `ollama` command available.
- **Linux:** Install Python 3.11 or newer using your distribution's package
  manager. On Debian/Ubuntu, virtual environments also need `python3-venv`.
  Follow the [official Ollama Linux installation guide](https://docs.ollama.com/linux).
  If its service is not running, open a separate terminal, run `ollama serve`,
  and leave that window open.

You need internet for installation and the model download. The default model
(`gemma3:4b`) downloads about 3.3 GB, plus the apps and Python packages; it needs
additional memory to run. Speed depends on your computer. For a smaller model,
see the troubleshooting section below. Local models do not need an Ollama account
or API key. See [Ollama's official getting-started guide](https://docs.ollama.com/quickstart).

## 3. Open a terminal in the Call Mac folder

Open the extracted folder containing **app.py**, **README.md**, and
**requirements.txt**. This is the project folder used throughout this guide.

- **Windows:** Right-click inside the folder and choose **Open in Terminal**.
  Use PowerShell for the commands below.
- **macOS:** Open Terminal from Applications → Utilities. Type `cd ` (including
  the space), drag the Call Mac folder from Finder into the window, then press Enter.
- **Linux:** In your file manager, open the folder and choose **Open in Terminal**
  from its right-click menu, if available. Otherwise open Terminal and use
  `cd "/full/path/to/Call-Mac"`, replacing the path with your extracted folder.

Check Python before continuing:

**Windows:**

```powershell
py -3 --version
```

**macOS / Linux:**

```bash
python3 --version
```

You should see `Python 3.11` or newer. If the command is missing or the version is
older, return to the Python installation step.

## 4. Install Call Mac's supporting packages

These commands create a `.venv` folder for Call Mac's Python packages and install
them there. You only need this step the first time, or after requirements change.

**Windows PowerShell:**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**macOS / Linux:**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Wait for installation to finish and the terminal to accept another command.
These commands use the environment directly; there is no activation step.

## 5. Download the AI model

With Ollama open or its server running, enter:

```text
ollama pull gemma3:4b
```

This downloads the AI model once. Leave the window open until it finishes.
You do not need to download it every time you use Call Mac.

## 6. Open Call Mac

In the same project terminal, run the command for your computer:

**Windows PowerShell:**

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

**macOS / Linux:**

```bash
.venv/bin/python -m streamlit run app.py
```

If Streamlit asks for an email, you can leave it blank and press Enter.
Your browser should open. If it does not, open **http://localhost:8501** yourself.
Keep the terminal open while using Call Mac.

1. Open the sidebar using the hamburger menu at the top left.
2. Expand **AI connection** and click **Test connection**. A successful check
   means Call Mac can reach Ollama and find the selected model.
3. Leave the user as **Guest** and choose **Beginner** for your experience.
4. Type a question, such as “My printer says offline,” and submit it.
5. Follow the next step and tell Call Mac what happened. The first answer can
   take longer while Ollama loads the model.

Guest conversations are temporary. To keep your history and successful fixes,
create a profile under **Saved profiles** and click **Save profile**. It applies
that profile automatically. These records stay on this computer.

## Next time you want help

Open Ollama. Open a terminal in your Call Mac folder and run the command from
step 6. You can skip installation and model download. On Linux, ensure the
Ollama service is running or keep `ollama serve` open in another terminal.

To stop Call Mac, click its terminal and press **Ctrl+C**. Closing the browser
alone does not stop the app. To restart it, run the same command again.

## Optional: use a different Ollama server

**Skip this when Ollama runs on this computer.** Call Mac already uses
`http://127.0.0.1:11434`. `127.0.0.1` means the computer running Call Mac;
`11434` is Ollama's usual port. This address is separate from the browser's
`http://localhost:8501` address.

If someone has set up Ollama on another computer for you, ask them for its
complete server address and installed model name. Then:

1. Copy **.env.example** to a new file named exactly **.env** in the project
   folder, beside **app.py**. Keep the original template.
2. Open **.env** in a plain text editor. On Windows, enable **File name extensions**
   in File Explorer so it does not accidentally become `.env.txt`.
3. Replace the `OLLAMA_BASE_URL` value with the address they gave you. Use a
   complete `http://` or `https://` address with the port if required, without
   `/api`, `/v1`, or other paths. Do not put it in Python code or in the README.
4. Set `CALL_MAC_MODEL` to a Gemma model installed on that server.
5. Save, stop Call Mac with **Ctrl+C**, and start it again. Click **Test connection**.

You can also copy the template from your project terminal:

**Windows PowerShell:**

```powershell
Copy-Item .env.example .env
notepad .env
```

**macOS / Linux:**

```bash
cp .env.example .env
```

Only copy when you do not already have an `.env`; preserve existing settings.
Lines starting with `#` are comments. Leave optional settings commented unless
needed. `OLLAMA_SECONDARY_URL` can provide a backup server. The advanced
`CALL_MAC_OLLAMA_URL` setting takes priority over `OLLAMA_BASE_URL`; environment
settings inherited by the terminal take priority over the `.env` file.

A remote server receives your problem, profile details, and relevant history.
Use a server you trust. Your saved database stays on the computer running Call Mac.
The `.env` file is ignored by Git; do not share it with private server details.

## If something goes wrong

| What you see | What to try |
| --- | --- |
| `py`, `python3`, or `ollama` is not recognized / command not found | Finish that app's installation, close the terminal, and open a new one. On Windows, try `python --version` if `py` is unavailable; if it shows 3.11 or newer, use `python` in place of `py -3`. |
| Can't find `requirements.txt` or `app.py` | Open a terminal in the extracted folder containing those files, then retry. |
| Linux cannot create the virtual environment | Install your distribution's matching Python venv package (Debian/Ubuntu: `sudo apt install python3-venv`), then retry step 4. |
| Call Mac can't reach Ollama | Open Ollama. On Linux, check its service or run `ollama serve` in a separate terminal. Retry **Test connection**. If using a remote server, ask its owner to check it. |
| `ollama serve` says the address is already in use | Ollama may already be running. Try **Test connection** before starting another server. |
| Model missing | Run `ollama pull gemma3:4b` on the computer running Ollama. In **AI connection**, use **Find installed Gemma models** and select it. |
| Answer is slow or model runs out of memory | Close other large apps. Download `gemma3:1b` with `ollama pull gemma3:1b`, then find and select it in **AI connection**. It is smaller but may give less capable advice. |
| Browser page won't load | Keep the Streamlit terminal open and check the local URL it prints; the port may differ if 8501 is busy. |
| Edited `.env` but nothing changed | Stop and restart Call Mac. Check the filename is `.env`, beside `app.py`, and that an advanced override is not set. |

To make the smaller model your startup default, copy `.env.example` to `.env`
as described above and change `CALL_MAC_MODEL=gemma3:1b`.

If you still need help, share the error text and your operating system. Remove
private addresses and personal information first; do not share your `.env` file.
