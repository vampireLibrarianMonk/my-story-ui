"""Transparent, deterministic intent suggestions. Never mutates canon."""

import re

MODES = ("explore", "draft", "continue", "character", "world", "research")

MODE_LABELS = {
    "explore": "Explore",
    "draft": "New chapter",
    "continue": "Continue writing",
    "character": "Character",
    "world": "Worldbuilding",
    "research": "Research",
}


def infer_mode(prompt: str) -> str:
    p = prompt.lower().strip()
    if not p:
        return "explore"
    if re.search(
        r"\b(resume|continue|pick up|carry on|finish|next scene|where we left off)\b", p
    ):
        return "continue"
    if re.search(
        r"\b(new chapter|start (a |the )?chapter|write chapter|draft (a |the )?chapter|chapter [0-9]+)\b",
        p,
    ):
        return "draft"
    if re.search(
        r"\b(research|sources?|historical(ly)?|fact.check|verify|evidence|references?|accurate|scholarship)\b",
        p,
    ):
        return "research"
    if re.search(
        r"\b(character|personality|motivation|arc|protagonist|antagonist|relationship|dialogue|backstory)\b",
        p,
    ):
        return "character"
    if re.search(
        r"\b(world.?build|kingdom|faction|religion|culture|politics|magic system|geography|empire|institution|society|tribe)\b",
        p,
    ):
        return "world"
    return "explore"


WIDGETS = {
    "explore": [
        {
            "key": "approach",
            "label": "Approach",
            "type": "select",
            "choices": [
                "Discuss possibilities",
                "Compare alternatives",
                "Challenge assumptions",
                "Ask questions",
            ],
        },
        {
            "key": "output",
            "label": "Deliverable",
            "type": "select",
            "choices": ["Conversation", "Idea list", "Short outline", "Draft passage"],
        },
    ],
    "draft": [
        {
            "key": "point_of_view",
            "label": "Point of view",
            "type": "select",
            "choices": [
                "Third person limited",
                "Third person omniscient",
                "First person",
            ],
        },
        {
            "key": "tone",
            "label": "Tone",
            "type": "select",
            "choices": [
                "Literary and restrained",
                "Atmospheric",
                "Urgent",
                "Reflective",
            ],
        },
        {
            "key": "length",
            "label": "Scope",
            "type": "select",
            "choices": ["Opening paragraphs", "Full scene", "Chapter outline"],
        },
    ],
    "continue": [
        {
            "key": "direction",
            "label": "Next step",
            "type": "select",
            "choices": [
                "Continue directly",
                "Bridge to next scene",
                "Suggest three paths",
                "Revise last passage",
            ],
        },
        {
            "key": "consistency",
            "label": "Continuity",
            "type": "select",
            "choices": [
                "Preserve voice and facts",
                "Preserve facts; explore tone",
                "Suggest alternatives",
            ],
        },
    ],
    "character": [
        {
            "key": "focus",
            "label": "Focus",
            "type": "select",
            "choices": [
                "Motivations",
                "Dialogue",
                "Relationships",
                "Biography",
                "Character arc",
            ],
        },
        {
            "key": "format",
            "label": "Format",
            "type": "select",
            "choices": ["Discuss", "Profile notes", "Scene experiment", "Interview"],
        },
    ],
    "world": [
        {
            "key": "domain",
            "label": "Domain",
            "type": "select",
            "choices": [
                "Politics and factions",
                "Religion",
                "History",
                "Geography",
                "Culture",
                "Institutions",
                "Magic and rules",
            ],
        },
        {
            "key": "lens",
            "label": "Lens",
            "type": "select",
            "choices": [
                "Generate possibilities",
                "Test internal consistency",
                "Deepen realism",
                "Compare alternatives",
            ],
        },
    ],
    "research": [
        {
            "key": "method",
            "label": "Research approach",
            "type": "select",
            "choices": [
                "Establish what is known",
                "Compare interpretations",
                "Identify sources to consult",
                "Separate fact from invention",
            ],
        },
        {
            "key": "rigor",
            "label": "Uncertainty",
            "type": "select",
            "choices": ["Label uncertain claims", "Challenge all unsupported claims"],
        },
    ],
}

SYSTEM = {
    "explore": "Collaborate conversationally. Ask one useful question when it will help. Distinguish suggestions from established fictional facts.",
    "draft": "Act as a thoughtful prose collaborator. Draft fiction in the requested voice and scope. Do not treat generated prose as approved canon.",
    "continue": "Continue the supplied writing faithfully, preserving characters, events, and tone in the provided excerpts. If no preceding chapter is supplied, state that limitation rather than inventing its contents.",
    "character": "Help explore character motivations, relationships, and dialogue. Distinguish proposed traits from established character details.",
    "world": "Help develop coherent fictional institutions, societies, timelines, religions, and political systems. Challenge internal contradictions.",
    "research": "Research carefully using only knowledge and provided materials. Distinguish evidence, uncertainty, and creative speculation. Do not fabricate citations or imply live web access.",
}
