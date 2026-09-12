from pathlib import Path
import subprocess


# ============================================================
# WORKSPACE
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE = (BASE_DIR / "workspace").resolve()


# ============================================================
# SAFE PATH
# ============================================================

def safe_path(relative_path):
    """
    Convert a workspace-relative path into an absolute path.

    Prevents the agent from accessing files outside the
    workspace directory.
    """

    path = (WORKSPACE / relative_path).resolve()

    try:
        path.relative_to(WORKSPACE)
    except ValueError:
        raise ValueError(
            f"Access outside workspace is not allowed: {relative_path}"
        )

    return path


# ============================================================
# LIST DIRECTORY
# ============================================================

def list_directory(relative_path="."):
    """
    List files and directories inside the workspace.
    """

    path = safe_path(relative_path)

    if not path.exists():
        return f"Path does not exist: {relative_path}"

    if not path.is_dir():
        return f"Not a directory: {relative_path}"

    items = []

    for item in sorted(path.iterdir(), key=lambda x: x.name.lower()):

        if item.is_dir():
            items.append(f"[DIR]  {item.name}/")
        else:
            items.append(f"[FILE] {item.name}")

    if not items:
        return "(empty directory)"

    return "\n".join(items)


# ============================================================
# READ FILE
# ============================================================

def read_file(relative_path):
    """
    Read a text file inside the workspace.
    """

    path = safe_path(relative_path)

    if not path.exists():
        return f"File does not exist: {relative_path}"

    if not path.is_file():
        return f"Not a file: {relative_path}"

    try:
        content = path.read_text(encoding="utf-8")

    except UnicodeDecodeError:
        return f"Cannot read {relative_path}: unsupported text encoding."

    except PermissionError:
        return f"Permission denied: {relative_path}"

    return content


# ============================================================
# WRITE FILE
# ============================================================

def write_file(relative_path, content):
    """
    Create or overwrite a text file inside the workspace.
    """

    path = safe_path(relative_path)

    # Create parent directories if required
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        path.write_text(
            content,
            encoding="utf-8"
        )

    except PermissionError:
        return f"Permission denied while writing: {relative_path}"

    except OSError as e:
        return f"Failed to write {relative_path}: {e}"

    # Verify that the file was actually written
    if not path.exists():
        return f"Write failed: {relative_path} does not exist after writing."

    try:
        saved_content = path.read_text(encoding="utf-8")

    except Exception as e:
        return f"File was written but could not be verified: {e}"

    if saved_content != content:
        return (
            f"Write verification failed for {relative_path}. "
            "File contents do not match the requested content."
        )

    return f"Successfully wrote and verified: {relative_path}"


# ============================================================
# SEARCH FILES
# ============================================================

def search_files(query):
    """
    Search for a text string in files inside the workspace.

    Returns matching file paths, line numbers, and lines.
    """

    if not query.strip():
        return "Search query cannot be empty."

    results = []

    ignored_directories = {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".idea",
        ".vscode",
    }

    for path in WORKSPACE.rglob("*"):

        if not path.is_file():
            continue

        # Ignore unnecessary directories
        if any(
            part in ignored_directories
            for part in path.parts
        ):
            continue

        try:
            content = path.read_text(encoding="utf-8")

        except (
            UnicodeDecodeError,
            PermissionError,
            OSError
        ):
            continue

        for line_number, line in enumerate(
            content.splitlines(),
            start=1
        ):

            if query.lower() in line.lower():

                relative_path = path.relative_to(WORKSPACE)

                results.append(
                    f"{relative_path}:{line_number}: {line.strip()}"
                )

    if not results:
        return f"No matches found for: {query}"

    return "\n".join(results)


# ============================================================
# RUN COMMAND
# ============================================================

def run_command(command):
    """
    Run a shell command inside the workspace.

    Output from stdout, stderr, and exit code is returned
    to the agent.
    """

    if not command.strip():
        return "Command cannot be empty."

    try:

        result = subprocess.run(
            command,
            shell=True,
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=60,
        )

    except subprocess.TimeoutExpired:
        return (
            "Command timed out after 60 seconds."
        )

    except Exception as e:
        return f"Failed to execute command: {e}"

    output_parts = []

    if result.stdout:
        output_parts.append(
            f"STDOUT:\n{result.stdout}"
        )

    if result.stderr:
        output_parts.append(
            f"STDERR:\n{result.stderr}"
        )

    output_parts.append(
        f"EXIT CODE: {result.returncode}"
    )

    return "\n\n".join(output_parts)