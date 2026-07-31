from pathlib import Path

import update_structure


def test_structure_block_keeps_blank_lines_inside_markers(
    tmp_path: Path, monkeypatch
) -> None:
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        "# Test\n\n"
        "<!-- STRUCTURE:START -->\n"
        "```\nold/\n```\n"
        "<!-- STRUCTURE:END -->\n"
    )
    monkeypatch.setattr(update_structure, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(update_structure, "tracked_files", lambda root: ["README.md"])

    assert update_structure.main() == 0

    content = agents.read_text()
    assert "<!-- STRUCTURE:START -->\n\n```\n" in content
    assert "\n```\n\n<!-- STRUCTURE:END -->" in content
