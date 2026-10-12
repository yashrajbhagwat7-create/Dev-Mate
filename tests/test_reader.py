"""Unit tests for InputReader, file loading, and @file expansion."""

import pytest
from pathlib import Path
from devmate.reader import InputReader


@pytest.fixture
def reader_workspace(tmp_path):
    (tmp_path / "instructions.txt").write_text("Refactor authentication to use JWT tokens.", encoding="utf-8")
    (tmp_path / "config.json").write_text('{"auth": "bearer"}', encoding="utf-8")
    reader = InputReader(tmp_path)
    return tmp_path, reader


def test_load_from_file(reader_workspace):
    tmp_path, reader = reader_workspace
    loaded = reader.load_from_file("/file instructions.txt")
    assert "Refactor authentication to use JWT tokens." in loaded

    loaded_with_extra = reader.load_from_file("/file instructions.txt Implement this immediately")
    assert "Implement this immediately" in loaded_with_extra
    assert "Refactor authentication to use JWT tokens." in loaded_with_extra


def test_load_from_nonexistent_file(reader_workspace):
    _, reader = reader_workspace
    loaded = reader.load_from_file("/file nonexistent.txt")
    assert loaded == ""


def test_inline_file_expansion(reader_workspace):
    tmp_path, reader = reader_workspace
    prompt = "Please inspect @config.json and check @instructions.txt"
    processed = reader.process_special_syntax(prompt)

    assert "config.json" in processed
    assert "instructions.txt" in processed
    assert '{"auth": "bearer"}' in processed
    assert "Refactor authentication to use JWT tokens." in processed


def test_process_special_syntax_no_files(reader_workspace):
    _, reader = reader_workspace
    prompt = "Hello world without any file references"
    assert reader.process_special_syntax(prompt) == prompt
