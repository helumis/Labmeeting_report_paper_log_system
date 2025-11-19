from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime, date

# ----------------------------
# Paper ↔ Author 多對多
# ----------------------------
class PaperAuthorLink(SQLModel, table=True):
    paper_id: Optional[int] = Field(default=None, foreign_key="paper.id", primary_key=True)
    author_id: Optional[int] = Field(default=None, foreign_key="author.id", primary_key=True)

# ----------------------------
# Author ↔ Affiliation 多對多
# ----------------------------
class AuthorAffiliationLink(SQLModel, table=True):
    author_id: Optional[int] = Field(default=None, foreign_key="author.id", primary_key=True)
    affiliation_id: Optional[int] = Field(default=None, foreign_key="affiliation.id", primary_key=True)

# ----------------------------
# Paper ↔ Tag 多對多
# ----------------------------
class PaperTag(SQLModel, table=True):
    paper_id: Optional[int] = Field(default=None, foreign_key="paper.id", primary_key=True)
    tag_id: Optional[int] = Field(default=None, foreign_key="tag.id", primary_key=True)

# ----------------------------
# Author
# ----------------------------
class Author(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str

    papers: List["Paper"] = Relationship(back_populates="authors", link_model=PaperAuthorLink)
    affiliations: List["Affiliation"] = Relationship(back_populates="authors", link_model=AuthorAffiliationLink)

# ----------------------------
# Affiliation
# ----------------------------
class Affiliation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str

    authors: List[Author] = Relationship(back_populates="affiliations", link_model=AuthorAffiliationLink)

# ----------------------------
# Paper
# ----------------------------
class Paper(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    paper_title: str
    published_year: int
    published_month: int
    journal_or_conference: str

    authors: List[Author] = Relationship(back_populates="papers", link_model=PaperAuthorLink)
    tags: List["Tag"] = Relationship(back_populates="papers", link_model=PaperTag)
    reports: List["Report"] = Relationship(back_populates="paper")

# ----------------------------
# User
# ----------------------------
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str
    display_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    reports: List["Report"] = Relationship(back_populates="user")
    comments: List["Comment"] = Relationship(back_populates="user")

# ----------------------------
# LabMeeting
# ----------------------------
class LabMeeting(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_title: str
    meeting_date: date
    meeting_location: str

    reports: List["Report"] = Relationship(back_populates="meeting")

# ----------------------------
# Tag
# ----------------------------
class Tag(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str

    papers: List[Paper] = Relationship(back_populates="tags", link_model=PaperTag)

# ----------------------------
# Report
# ----------------------------
class Report(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    report_title: str
    report_summary: str
    slides_link: str
    user_id: int = Field(foreign_key="user.id")
    meeting_id: int = Field(foreign_key="labmeeting.id")
    paper_id: Optional[int] = Field(default=None, foreign_key="paper.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    user: Optional[User] = Relationship(back_populates="reports")
    meeting: Optional[LabMeeting] = Relationship(back_populates="reports")
    paper: Optional[Paper] = Relationship(back_populates="reports")
    comments: List["Comment"] = Relationship(back_populates="report")

# ----------------------------
# Comment
# ----------------------------
class Comment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    report_id: int = Field(foreign_key="report.id")
    user_id: int = Field(foreign_key="user.id")
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    report: Optional[Report] = Relationship(back_populates="comments")
    user: Optional[User] = Relationship(back_populates="comments")
