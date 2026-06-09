#!/usr/bin/env python3
"""UserPromptSubmit hook: classify user messages and inject routing hints.

Reads JSON from stdin with schema: {"message": {"role": "user", "content": "..."}}
Prints routing hints to stdout (injected into Claude's context).
"""
import json
import sys
import re


def classify(text: str) -> list:
    """Return list of detected content categories."""
    categories = []
    t = text.lower()

    # Stakeholder mentions — wikilink patterns or known name patterns
    # Stakeholder name list — populate this with the names your classifier should
    # detect as routing hints. Each match adds a hint to the system reminder.
    STAKEHOLDER_NAMES: list[str] = []  # e.g. ["alice smith", "bob jones"]
    name_pattern = '|'.join(re.escape(n) for n in STAKEHOLDER_NAMES) if STAKEHOLDER_NAMES else None
    if re.search(r'\[\[.+?\]\]', text) or (name_pattern and re.search(rf'\b({name_pattern})\b', t)):
        categories.append('stakeholder')

    # Meeting content
    if re.search(r'\b(meeting|met with|discussed with|catch-?up|bila|1-on-1|afdelingsoverleg|overleg)\b', t):
        categories.append('meeting')

    # Decision signals
    if re.search(r'\b(we decided|agreed to|decision:|resolved|will not|we will focus)\b', t):
        categories.append('decision')

    # Action items
    if re.search(r'\b(action:|todo|need to follow[- ]up|arrange meeting|request meeting|send email|write email)\b', t):
        categories.append('action')

    # Diary / personal content — Chinese characters or personal keywords
    if re.search(r'[\u4e00-\u9fff]', text) or re.search(
        r'\b(diary|journal|feeling|felt|emotion|frustrat|anxious|happy|grateful)\b', t
    ):
        categories.append('personal')

    # Project update — add your own project keywords here
    PROJECT_KEYWORDS: list[str] = []  # e.g. ["myproject", "charter", "milestone"]
    if PROJECT_KEYWORDS:
        project_pattern = '|'.join(re.escape(k) for k in PROJECT_KEYWORDS)
        if re.search(rf'\b({project_pattern})\b', t):
            categories.append('project')

    return categories


def build_hints(categories: list) -> str:
    """Build routing hint string from detected categories."""
    hints = []

    if 'stakeholder' in categories:
        hints.append(
            'Stakeholder mentioned. Consider updating their file in '
            '20-Work/Stakeholders/ (context log entry) and check if '
            '30-Projects/<MyProject>/<MyProject>.md needs a change log update.'
        )

    if 'meeting' in categories:
        hints.append(
            'Meeting content detected. If this is a new meeting, create a note '
            'in 20-Work/Meetings/YYYY-MM-DD-<slug>.md with standard frontmatter '
            '(type, date, title, people, org, project, topic, tags).'
        )

    if 'decision' in categories:
        hints.append(
            'Decision detected. Record in the relevant project file '
            '(30-Projects/) under Open Decisions or Change Log. '
            'Update work_patterns.md if this reveals a decision-making pattern.'
        )

    if 'action' in categories:
        hints.append(
            'Action item detected. Add as a checkbox (- [ ]) in the relevant '
            'meeting note or project file.'
        )

    if 'personal' in categories:
        hints.append(
            'Personal/diary content detected. If this is a diary entry, save to '
            '40-Life/Hypomnemata/YYYY-MM-DD.md. Update me_patterns.md if this '
            'reveals an emotional or identity pattern.'
        )

    if 'project' in categories:
        hints.append(
            '<MyProject>/<funder-programme> content detected. Check if '
            '30-Projects/<MyProject>/<MyProject>.md needs updating '
            '(Status at a Glance, Open Decisions, Next Actions, Change Log).'
        )

    return ' | '.join(hints)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    # Extract message content
    message = data.get('message', {})
    content = ''
    if isinstance(message, dict):
        content = message.get('content', '')
        if isinstance(content, list):
            content = ' '.join(
                block.get('text', '') for block in content
                if isinstance(block, dict)
            )
    elif isinstance(message, str):
        content = message

    if not content or len(content) < 10:
        return

    categories = classify(content)
    if not categories:
        return

    hints = build_hints(categories)
    if hints:
        print(f'[Vault routing hints: {hints}]')


if __name__ == '__main__':
    main()
