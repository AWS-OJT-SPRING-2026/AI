from pydantic import BaseModel
from typing import List, Optional


class Subsection(BaseModel):
    subsection_number: str
    subsection_title: Optional[str] = None
    content_blocks: Optional[List[str]] = None


class Section(BaseModel):
    section_number: str
    section_title: Optional[str] = None
    subsections: Optional[List[Subsection]] = None


class Lesson(BaseModel):
    lesson_number: str
    title: str
    keywords: Optional[List[str]] = None
    section: List[Section]


class Chapter(BaseModel):
    chapter_number: str
    title: str
    lessons: List[Lesson]


class Book(BaseModel):
    book_name: str
    chapters: List[Chapter]
