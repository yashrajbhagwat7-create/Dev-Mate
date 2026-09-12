from llm import call_llm
from tools import (
    list_directory,
    read_file,
    write_file,
    search_files,
)


SYSTEM_PROMPT = """
You are a project-aware coding assistant.

You have access to a software project's files.

Available tool requests:

LIST

READ: relative/path/to/file.py

SEARCH: text_to_search

WRITE: relative/path/to/file.py

Rules:

- Never invent file contents.
- Read relevant files before proposing changes.
- Use SEARCH when you don't know which file contains something.
- Before using WRITE, explain what you want to change and ask the user for approval.
- Never assume the user approved a change.
- Do not write files without explicit user approval.
- Keep your responses concise and practical.

Tool requests may optionally be wrapped in:

<tool_call>...</tool_call>

Examples:

LIST

<tool_call>LIST</tool_call>

READ: src/model.py

<tool_call>READ: src/model.py</tool_call>

SEARCH: RandomForestClassifier

<tool_call>SEARCH: RandomForestClassifier</tool_call>
"""


def handle_assistant_response(response, messages):

    response = response.strip()

    # -------------------------
    # LIST
    # -------------------------

    if response == "LIST" or "<tool_call>LIST</tool_call>" in response:

        result = list_directory(".")

        messages.append({
            "role": "user",
            "content": f"PROJECT STRUCTURE:\n{result}"
        })

        return True

    # -------------------------
    # READ
    # -------------------------

    if "READ:" in response:

        start = response.find("READ:")
        path = response[start + len("READ:"):]

        if "</tool_call>" in path:
            path = path.split("</tool_call>")[0]

        path = path.strip()

        result = read_file(path)

        messages.append({
            "role": "user",
            "content": f"FILE: {path}\n\n{result}"
        })

        return True

    # -------------------------
    # SEARCH
    # -------------------------

    if "SEARCH:" in response:

        start = response.find("SEARCH:")
        query = response[start + len("SEARCH:"):]

        if "</tool_call>" in query:
            query = query.split("</tool_call>")[0]

        query = query.strip()

        result = search_files(query)

        messages.append({
            "role": "user",
            "content": f"SEARCH RESULTS FOR: {query}\n\n{result}"
        })

        return True

    return False


def main():

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    print("Dev Assistant")
    print("Commands:")
    print("  /list")
    print("  /read <file>")
    print("  /search <text>")
    print("  exit")
    print()

    while True:

        user_input = input("You: ").strip()

        if user_input.lower() == "exit":
            break

        # -------------------------
        # Manual LIST
        # -------------------------

        if user_input == "/list":

            result = list_directory(".")

            print("\nPROJECT STRUCTURE:")
            print(result)
            print()

            continue

        # -------------------------
        # Manual READ
        # -------------------------

        if user_input.startswith("/read "):

            path = user_input[6:].strip()

            result = read_file(path)

            print(f"\n--- {path} ---")
            print(result)
            print()

            continue

        # -------------------------
        # Manual SEARCH
        # -------------------------

        if user_input.startswith("/search "):

            query = user_input[8:].strip()

            result = search_files(query)

            print("\nSEARCH RESULTS:")
            print(result)
            print()

            continue

        # -------------------------
        # Normal conversation
        # -------------------------

        messages.append({
            "role": "user",
            "content": user_input,
        })

        while True:

            response = call_llm(messages)

            print(f"\nAssistant:\n{response}\n")

            # Tool request
            if handle_assistant_response(response, messages):
                continue

            # Final answer
            messages.append({
                "role": "assistant",
                "content": response,
            })

            break


if __name__ == "__main__":
    main()