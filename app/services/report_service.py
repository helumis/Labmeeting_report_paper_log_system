"""
報告服務 - 完整修正版（支持編輯時創建 Meeting）
app/services/report_service.py
"""
from datetime import datetime
from typing import Optional
from fastapi import HTTPException
from sqlmodel import Session, select

from ..models import Report, LabMeeting, Comment
from ..utils.validators import safe_str, is_valid_id
from .paper_service import PaperService

class ReportService:
    """報告服務類"""
    
    def __init__(self, session: Session):
        self.session = session
        self.paper_service = PaperService(session)
    
    def create_or_get_meeting(self, form) -> Optional[int]:
        """創建或獲取會議
        
        優先級：
        1. 如果提供了有效的 existing_meeting_id，使用它
        2. 如果提供了 meeting_title，創建新會議
        3. 否則返回 None
        
        Returns:
            會議 ID，如果無法創建或獲取則返回 None
        """
        # 優先檢查是否選擇了現有會議
        existing_meeting_id = form.get("existing_meeting_id")
        if is_valid_id(existing_meeting_id):
            return int(existing_meeting_id)
        
        # 如果沒有選擇現有會議，嘗試創建新會議
        meeting_title = safe_str(form.get("meeting_title"))
        if not meeting_title:
            return None
        
        # 創建新會議
        meeting = LabMeeting(
            meeting_title=meeting_title,
            meeting_location=safe_str(form.get("meeting_location")),
            meeting_date=datetime.now().date()
        )
        
        # 解析會議日期
        meeting_date_str = form.get("meeting_date")
        if meeting_date_str:
            try:
                meeting.meeting_date = datetime.fromisoformat(
                    str(meeting_date_str)
                ).date()
            except Exception as e:
                print(f"解析會議日期時出錯: {e}")
        
        self.session.add(meeting)
        self.session.commit()
        self.session.refresh(meeting)
        
        return meeting.id
    
    def create_or_get_paper(self, form) -> Optional[int]:
        """創建或獲取論文
        
        優先級：
        1. 如果提供了有效的 existing_paper_id，使用它
        2. 如果提供了 paper_title，創建新論文
        3. 否則返回 None
        
        Returns:
            論文 ID，如果無法創建或獲取則返回 None
        """
        # 優先檢查是否選擇了現有論文
        existing_paper_id = form.get("existing_paper_id") or form.get("paper_id")
        if is_valid_id(existing_paper_id):
            return int(existing_paper_id)
        
        # 如果沒有選擇現有論文，嘗試創建新論文
        if safe_str(form.get("paper_title")):
            return self.paper_service.create_or_update_paper(form)
        
        return None
    
    def create_report(self, form, user_id: int) -> Report:
        """創建新報告
        
        Args:
            form: 表單資料
            user_id: 使用者 ID
            
        Returns:
            創建的報告物件
            
        Raises:
            HTTPException: 當必要欄位缺失時
        """
        report_title = safe_str(form.get("report_title"))
        if not report_title:
            raise HTTPException(status_code=400, detail="報告標題不能為空")
        
        # 獲取或創建會議
        meeting_id = self.create_or_get_meeting(form)
        if not meeting_id:
            raise HTTPException(status_code=400, detail="必須選擇或創建會議")
        
        # 獲取或創建論文（可選）
        paper_id = self.create_or_get_paper(form)
        
        report = Report(
            report_title=report_title,
            report_summary=safe_str(form.get("report_summary")),
            slides_link=safe_str(form.get("slides_link")),
            user_id=user_id,
            meeting_id=meeting_id,
            paper_id=paper_id
        )
        
        self.session.add(report)
        self.session.commit()
        self.session.refresh(report)
        
        return report
    
    def update_report(self, report: Report, form) -> Report:
        """更新報告
        
        Args:
            report: 要更新的報告物件
            form: 表單資料
            
        Returns:
            更新後的報告物件
            
        Raises:
            HTTPException: 當必要欄位缺失時
        """
        # 更新基本資訊
        report_title = safe_str(form.get("report_title"))
        if not report_title:
            raise HTTPException(status_code=400, detail="報告標題不能為空")
        
        report.report_title = report_title
        report.report_summary = safe_str(form.get("report_summary"))
        report.slides_link = safe_str(form.get("slides_link"))
        
        # 更新會議（現在支持創建新會議）
        new_meeting_id = self.create_or_get_meeting(form)
        if new_meeting_id:
            report.meeting_id = new_meeting_id
        # 如果 new_meeting_id 為 None，保持原來的 meeting_id
        
        # 更新論文
        # 優先檢查是否選擇了現有論文
        existing_paper_id = form.get("existing_paper_id")
        if is_valid_id(existing_paper_id):
            report.paper_id = int(existing_paper_id)
        # 如果沒有選擇現有論文，檢查是否要編輯當前論文
        elif safe_str(form.get("paper_title")):
            # 傳遞現有的 paper_id 以進行更新
            report.paper_id = self.paper_service.create_or_update_paper(
                form, 
                report.paper_id
            )
        else:
            # 如果所有論文欄位都是空的，移除論文關聯
            report.paper_id = None
        
        self.session.add(report)
        self.session.commit()
        self.session.refresh(report)
        
        return report
    
    def delete_report(self, report_id: int):
        """刪除報告
        
        Args:
            report_id: 報告 ID
            
        Raises:
            HTTPException: 當報告不存在時
        """
        report = self.session.get(Report, report_id)
        if not report:
            raise HTTPException(status_code=404, detail="報告不存在")
        
        # 刪除關聯的評論
        comments = self.session.exec(
            select(Comment).where(Comment.report_id == report_id)
        ).all()
        
        for comment in comments:
            self.session.delete(comment)
        
        self.session.delete(report)
        self.session.commit()
    
    def get_report_by_id(self, report_id: int) -> Report:
        """根據 ID 獲取報告
        
        Args:
            report_id: 報告 ID
            
        Returns:
            報告物件
            
        Raises:
            HTTPException: 當報告不存在時
        """
        report = self.session.get(Report, report_id)
        if not report:
            raise HTTPException(status_code=404, detail="報告不存在")
        return report