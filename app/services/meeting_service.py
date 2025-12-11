#meeting_service.py
"""
會議服務
負責會議的 CRUD 操作
"""
from datetime import datetime, date
from typing import List, Optional
from fastapi import HTTPException
from sqlmodel import Session, select

from ..models import LabMeeting, Report
from ..utils.validators import safe_str, validate_required_field

class MeetingService:
    """會議服務類"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_all_meetings(self, limit: int = 100) -> List[LabMeeting]:
        """獲取所有會議
        
        Args:
            limit: 返回數量限制
            
        Returns:
            會議列表
        """
        stmt = (
            select(LabMeeting)
            .order_by(LabMeeting.meeting_date.desc())
            .limit(limit)
        )
        return list(self.session.exec(stmt).all())
    
    def get_meeting_by_id(self, meeting_id: int) -> LabMeeting:
        """根據 ID 獲取會議
        
        Args:
            meeting_id: 會議 ID
            
        Returns:
            會議物件
            
        Raises:
            HTTPException: 當會議不存在時
        """
        meeting = self.session.get(LabMeeting, meeting_id)
        if not meeting:
            raise HTTPException(status_code=404, detail="會議不存在")
        return meeting
    
    def create_meeting(
        self,
        meeting_title: str,
        meeting_date: date,
        meeting_location: str = ""
    ) -> LabMeeting:
        """創建新會議
        
        Args:
            meeting_title: 會議標題
            meeting_date: 會議日期
            meeting_location: 會議地點
            
        Returns:
            創建的會議物件
            
        Raises:
            ValueError: 當必填欄位缺失時
        """
        # 驗證必填欄位
        meeting_title = validate_required_field(meeting_title, "會議標題")
        
        if not meeting_date:
            raise ValueError("會議日期不能為空")
        
        meeting = LabMeeting(
            meeting_title=meeting_title,
            meeting_date=meeting_date,
            meeting_location=safe_str(meeting_location)
        )
        
        self.session.add(meeting)
        self.session.commit()
        self.session.refresh(meeting)
        
        return meeting
    
    def update_meeting(
        self,
        meeting_id: int,
        meeting_title: Optional[str] = None,
        meeting_date: Optional[date] = None,
        meeting_location: Optional[str] = None
    ) -> LabMeeting:
        """更新會議資訊
        
        Args:
            meeting_id: 會議 ID
            meeting_title: 新的會議標題
            meeting_date: 新的會議日期
            meeting_location: 新的會議地點
            
        Returns:
            更新後的會議物件
        """
        meeting = self.get_meeting_by_id(meeting_id)
        
        if meeting_title is not None:
            meeting.meeting_title = validate_required_field(meeting_title, "會議標題")
        
        if meeting_date is not None:
            meeting.meeting_date = meeting_date
        
        if meeting_location is not None:
            meeting.meeting_location = safe_str(meeting_location)
        
        self.session.add(meeting)
        self.session.commit()
        self.session.refresh(meeting)
        
        return meeting
    
    def delete_meeting(self, meeting_id: int, force: bool = False):
        """刪除會議
        
        Args:
            meeting_id: 會議 ID
            force: 是否強制刪除（即使有關聯的報告）
            
        Raises:
            HTTPException: 當會議不存在或有關聯報告時
        """
        meeting = self.get_meeting_by_id(meeting_id)
        
        # 檢查是否有關聯的報告
        reports_count = self.session.exec(
            select(Report).where(Report.meeting_id == meeting_id)
        ).first()
        
        if reports_count and not force:
            raise HTTPException(
                status_code=400,
                detail="此會議下還有報告，無法刪除。請先刪除所有相關報告。"
            )
        
        # 如果強制刪除，先將所有報告的 meeting_id 設為 None
        if force:
            reports = self.session.exec(
                select(Report).where(Report.meeting_id == meeting_id)
            ).all()
            for report in reports:
                report.meeting_id = None
                self.session.add(report)
            self.session.commit()
        
        self.session.delete(meeting)
        self.session.commit()
    
    def get_meeting_reports(self, meeting_id: int) -> List[Report]:
        """獲取會議的所有報告
        
        Args:
            meeting_id: 會議 ID
            
        Returns:
            報告列表
        """
        stmt = (
            select(Report)
            .where(Report.meeting_id == meeting_id)
            .order_by(Report.created_at.desc())
        )
        return list(self.session.exec(stmt).all())
    
    def get_meeting_stats(self, meeting_id: int) -> dict:
        """獲取會議統計資訊
        
        Args:
            meeting_id: 會議 ID
            
        Returns:
            包含統計資訊的字典
        """
        reports = self.get_meeting_reports(meeting_id)
        
        return {
            "total_reports": len(reports),
            "unique_presenters": len(set(r.user_id for r in reports)),
            "reports_with_papers": sum(1 for r in reports if r.paper_id)
        }