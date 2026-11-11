from enum import Enum
from pydantic import BaseModel, Field

class Domain(str, Enum):
    healthcare = "healthcare"
    transport = "transport"
    finance = "finance"
    education = "education"
    space = "space"
    utilities = "utilities"
    other = "other"

class Language(str, Enum):
    en = "en"
    uk = "uk"
    mixed = "mixed"

class ReqType(str, Enum):
    functional = "functional"
    non_functional = "non_functional"
    constraint = "constraint"
    interface = "interface"

class IsTestable(str, Enum):
    yes = "yes"
    partial = "partial"
    no = "no"

class Requirement(BaseModel):
    id: str | None = Field(
        default=None,
        description="Requirement identifier as written in the text (e.g. 'REQ-12'); null if absent",
    )
    section: str | None = Field(
        default=None,
        description=(
            "Heading path of the block the requirement belongs to: the title of its parent heading and of its "
            "nearest heading above it, as they appear in the excerpt, without section numbers, joined with ' > ' "
            "(e.g. 'Projection Object > Update'). At most two levels; only the nearest heading if it has no parent "
            "heading in the excerpt. null if no heading is printed above the requirement in the excerpt"
        ),
    )
    text: str = Field(description="The requirement statement, copied from the source exactly as written; only layout artifacts (numbering, page headers, line breaks) are removed")
    type: ReqType = Field(
        description=(
            "functional: what the system does; non_functional: quality attribute (performance, security, usability); "
            "constraint: imposed limit (technology, law, standard); interface: interaction with users or external systems"
        )
    )
    testable: IsTestable = Field(
        description="yes: a test can be derived directly; partial: needs clarification; no: too vague to test"
    )

class Extraction(BaseModel):
    doc_title: str | None = Field(default=None, description="Document title if present in the excerpt; otherwise null")
    domain: Domain = Field(description="Application domain of the system; 'other' if none fits")
    language: Language = Field(description="Language of the excerpt: en, uk, or mixed if both are present")
    actors: list[str] = Field(description="Users, roles or external systems that interact with the system")
    requirements: list[Requirement] = Field(description="All requirements found in the excerpt")  # nested list of objects
    has_acceptance_criteria: bool = Field(description="True if the excerpt contains explicit acceptance criteria")
    open_questions: list[str] = Field(
        description=(
            "Items the text itself marks as unresolved: explicit questions, TODO or placeholder notes "
            "(e.g. 'Specify required archive structure', 'How is X specified?'), copied or minimally rephrased; "
            "do not add your own analysis; empty list if the text marks none"
        )
    )
