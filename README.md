# Dev-Mate

A lightweight, multi-provider AI software-engineering agent for Windows/Linux/macOS.

## What it does
- OpenRouter + Google Gemini provider modes
- Reads, creates, edits and deletes project files
- Searches project files
- Executes commands and Python
- Runs tests
- Inspects git diff/status
- Human approval before risky actions
- Engineering loop: inspect -> plan -> edit -> execute -> diagnose -> verify -> checkpoint
- Every engineering iteration pauses for user approval by default
- Project-local `.devmate/` state and backups

## Quick start (Windows PowerShell)

```powershell
cd H:\dev_assistant\Dev-Mate
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
python -m devmate
```

Or install the launcher:

```powershell
pip install -e .
devmate
```

## API keys
Set either or both:

```env
OPENROUTER_API_KEY=...
GOOGLE_API_KEY=...
```

OpenRouter uses its OpenAI-compatible chat-completions API. Gemini uses Google's `generateContent` function-calling API.

## Modes
- `ask`: answer/explain, tools available but edits/commands ask for approval.
- `edit`: perform requested edits; risky actions still ask.
- `engineer`: iterate toward a goal and pause after every iteration.
- `autonomous`: same loop with higher iteration limit; it still pauses at checkpoints unless `AUTO_APPROVE_CHECKPOINTS=true`.

## Important safety model
The model never executes a tool itself. It requests a structured tool call; Dev-Mate validates permissions, executes the local function, and returns the result to the model.

For safety, delete, shell commands, package installation and git push require approval by default.

## Example

```text
devmate > Analyze this project and improve the Random Forest pipeline.
```

Dev-Mate will inspect the project, propose an iteration, make changes, run tests, report the result, and ask whether to continue.
