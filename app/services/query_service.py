#query_service.py
"""
查詢與統計服務
負責所有計數和資料豐富化邏輯
"""
from typing import List, Dict, Any, Optional
from sqlmodel import Session, select, func

from ..models import (
    Paper, Report, Tag, Author, Affiliation, User, LabMeeting,
    PaperTag, PaperAuthorLink, AuthorAffiliationLink, TagCountSnapshot
)

class QueryService:
    """查詢服務類"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_count(self, statement) -> int:
        """統一的計數查詢"""
        result = self.session.exec(statement).first()
        if result is None:
            return 0
        return result[0] if isinstance(result, tuple) else result
    
    def get_tag_count(self, tag_id: int) -> int:
        """獲取標籤計數"""
        stmt = select(TagCountSnapshot.count).where(
            TagCountSnapshot.tag_id == tag_id
        )
        return self.get_count(stmt)
    
    def get_author_count(self, author_id: int) -> int:
        """獲取作者論文計數"""
        stmt = (
            select(func.count(func.distinct(Paper.id)))
            .join(PaperAuthorLink, Paper.id == PaperAuthorLink.paper_id)
            .where(PaperAuthorLink.author_id == author_id)
        )
        return self.get_count(stmt)
    
    def get_affiliation_count(self, aff_id: int) -> int:
        """獲取機構論文計數"""
        stmt = (
            select(func.count(func.distinct(Paper.id)))
            .join(PaperAuthorLink, Paper.id == PaperAuthorLink.paper_id)
            .join(Author, PaperAuthorLink.author_id == Author.id)
            .join(AuthorAffiliationLink, Author.id == AuthorAffiliationLink.author_id)
            .where(AuthorAffiliationLink.affiliation_id == aff_id)
        )
        return self.get_count(stmt)
    
    def get_year_count(self, year: int) -> int:
        """獲取年份論文計數"""
        stmt = select(func.count(Paper.id)).where(Paper.published_year == year)
        return self.get_count(stmt)
    
    def get_venue_count(self, venue: str) -> int:
        """獲取期刊/會議論文計數"""
        stmt = select(func.count(Paper.id)).where(
            Paper.journal_or_conference == venue
        )
        return self.get_count(stmt)
    
    def enrich_paper_with_counts(self, paper: Paper) -> Optional[Dict[str, Any]]:
        """為論文添加計數資訊"""
        if not paper:
            return None
        
        # 豐富作者資訊
        enriched_authors = []
        for author in paper.authors:
            enriched_affs = [
                {
                    "aff": aff,
                    "count": self.get_affiliation_count(aff.id)
                }
                for aff in author.affiliations
            ]
            enriched_authors.append({
                "auth": author,
                "affiliations": enriched_affs,
                "count": self.get_author_count(author.id)
            })
        
        # 豐富標籤資訊
        enriched_tags = [
            {
                "tag": tag,
                "count": self.get_tag_count(tag.id)
            }
            for tag in paper.tags
        ]
        
        return {
            "paper": paper,
            "authors": enriched_authors,
            "tags": enriched_tags,
            "year_count": self.get_year_count(paper.published_year),
            "venue_count": self.get_venue_count(paper.journal_or_conference)
        }
    
    def enrich_reports(self, reports: List[Report]) -> List[Dict]:
        """豐富報告列表資訊"""
        enriched = []
        for r in reports:
            user = self.session.get(User, r.user_id) if r.user_id else None
            meeting = self.session.get(LabMeeting, r.meeting_id) if r.meeting_id else None
            paper = self.session.get(Paper, r.paper_id) if r.paper_id else None
            tags = paper.tags if paper else []
            enriched.append({
                "r": r,
                "user": user,
                "meeting": meeting,
                "paper": paper,
                "tags": tags
            })
        return enriched