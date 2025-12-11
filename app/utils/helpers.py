"""
輔助函數
"""
from typing import List, Dict
from sqlmodel import Session

from ..models import Report, User, LabMeeting, Paper

def enrich_reports_for_profile(
    session: Session, 
    reports: List[Report]
) -> List[Dict]:
    """為個人頁面豐富報告資訊"""
    enriched = []
    for r in reports:
        meeting = session.get(LabMeeting, r.meeting_id)
        paper = session.get(Paper, r.paper_id) if r.paper_id else None
        tags = paper.tags if paper else []
        enriched.append({
            "r": r,
            "meeting": meeting,
            "tags": tags
        })
    return enriched
