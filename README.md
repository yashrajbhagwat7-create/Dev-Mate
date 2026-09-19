# Dev-Mate

A lightweight, local-first AI software engineering agent for Windows, Linux, and macOS.

Dev-Mate helps developers inspect, understand, modify, run, test, and debug real software projects through natural language.

It is designed to be lightweight enough for low-resource machines while keeping the developer in control of what happens to their code.

---

## Why Dev-Mate?

Modern AI coding agents can write and modify code, but they can also make large changes without enough context or user control.

Dev-Mate is built around a different principle:

> **Understand the project → propose work → make controlled changes → verify the result → keep the developer in control.**

The agent can work with an existing project rather than requiring the developer to copy code into a chat.

---

## What Dev-Mate Can Do

### Project understanding

- Inspect the current project
- List project files
- Read source files
- Search across project files
- Build a project summary
- Maintain project-local memory
- Track recent development activity

### Code operations

- Create files
- Edit existing files
- Delete files with approval
- Create directories when required
- Back up files before modification

### Development operations

- Execute shell commands
- Run Python programs
- Run tests and checks
- Inspect `git status`
- Inspect `git diff`
- Diagnose command/test failures
- Iterate on engineering tasks

### AI providers

Dev-Mate currently supports:

- OpenRouter
- Google Gemini

The provider can be selected when starting Dev-Mate or changed during a session.

---

## How It Works

Dev-Mate follows an agentic development loop:

```text
User Request
     ↓
Understand Task
     ↓
Inspect Relevant Project Files
     ↓
Build Context
     ↓
AI Reasoning
     ↓
Tool Call
     ↓
Permission Check
     ↓
Execute Action
     ↓
Inspect Result
     ↓
Test / Verify
     ↓
Diagnose & Fix if Needed
     ↓
Checkpoint
     ↓
User Decides What Happens Next
