"""
Structured report format: goal -> data used -> analyses executed ->
findings -> confidence/limits -> next checks.
Used for the canned report path; the free-text `ask` path has the LLM
follow this same structure directly via its system prompt.
"""
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class Report:
    goal: str
    data_used: str
    analyses_executed: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    limits: list[str] = field(default_factory=list)
    next_checks: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [f"# Report: {self.goal}", "", "## Data used", self.data_used, "", "## Analyses executed"]
        lines += [f"- {a}" for a in self.analyses_executed]
        lines += ["", "## Findings"]
        lines += [f"- {f}" for f in self.findings]
        lines += ["", "## Confidence / limits"]
        lines += [f"- {l}" for l in self.limits]
        lines += ["", "## Suggested next checks"]
        lines += [f"- {n}" for n in self.next_checks]
        return "\n".join(lines)


def save_text_report(
    kind: str,
    question: str,
    answer_text: str,
    generated_files: list[str],
    reports_dir: str,
) -> Path:
    """Writes the agent's final answer - the LLM already follows the Report
    structure via its system prompt - plus links to any chart files it
    generated, to a timestamped Markdown file under `reports_dir`. Returns
    the file path.
    """
    out_dir = Path(reports_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"{kind}_{timestamp}.md"

    lines = [f"# Report: {kind}", "", f"**Question:** {question}", "", answer_text]

    if generated_files:
        lines += ["", "## Generated charts"]
        for file_path in generated_files:
            rel_path = os.path.relpath(file_path, start=out_dir)
            lines.append(f"![{Path(file_path).stem}]({rel_path})")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
