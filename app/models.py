from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship, Column, JSON
from datetime import datetime, date

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str
    display_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class LabMeeting(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    meeting_title: Optional[str] = None
    meeting_date: Optional[date] = None
    meeting_location: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Paper(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    paper_title: Optional[str] = None
    published_year: Optional[int] = None
    published_month: Optional[int] = None
    journal_or_conference: Optional[str] = None
    authors: Optional[str] = None
    affiliations: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Tag(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str

class ReportTag(SQLModel, table=True):
    report_id: Optional[int] = Field(default=None, foreign_key="report.id", primary_key=True)
    tag_id: Optional[int] = Field(default=None, foreign_key="tag.id", primary_key=True)

class Report(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    report_title: Optional[str] = None
    report_summary: Optional[str] = None
    slides_link: Optional[str] = None
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    meeting_id: Optional[int] = Field(default=None, foreign_key="labmeeting.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

class Comment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    report_id: Optional[int] = Field(default=None, foreign_key="report.id")
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    content: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
