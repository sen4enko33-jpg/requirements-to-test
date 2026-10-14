from enum import Enum
from pydantic import BaseModel

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
    id: str | None
    text: str
    type: ReqType
    testable: IsTestable

class Output(BaseModel):
    doc_title: str | None
    domain: Domain
    language: Language
    actors: list[str]
    requirements: list[Requirement] # nested list of objects
    has_acceptance_criteria: bool
    open_questions: list[str]