"""
論文服務 - 完整修正版
負責論文的 CRUD 和關聯處理
"""
from typing import Optional
from datetime import datetime
from sqlmodel import Session, select, delete

from ..models import (
    Paper, Author, Affiliation, Tag,
    PaperAuthorLink, AuthorAffiliationLink, PaperTag, TagCountSnapshot
)
from ..utils.validators import safe_int, safe_str

class PaperService:
    """論文服務類"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_or_create_author(self, name: str) -> Author:
        """獲取或創建作者"""
        name = name.strip()
        if not name:
            raise ValueError("作者名稱不能為空")
        
        author = self.session.exec(
            select(Author).where(Author.name == name)
        ).first()
        
        if not author:
            author = Author(name=name)
            self.session.add(author)
            self.session.commit()
            self.session.refresh(author)
        
        return author
    
    def get_or_create_affiliation(self, name: str) -> Affiliation:
        """獲取或創建機構"""
        name = name.strip()
        if not name:
            raise ValueError("機構名稱不能為空")
        
        aff = self.session.exec(
            select(Affiliation).where(Affiliation.name == name)
        ).first()
        
        if not aff:
            aff = Affiliation(name=name)
            self.session.add(aff)
            self.session.commit()
            self.session.refresh(aff)
        
        return aff
    
    def get_or_create_tag(self, name: str) -> Tag:
        """獲取或創建標籤"""
        name = name.strip()
        if not name:
            raise ValueError("標籤名稱不能為空")
        
        tag = self.session.exec(
            select(Tag).where(Tag.name == name)
        ).first()
        
        if not tag:
            tag = Tag(name=name)
            self.session.add(tag)
            self.session.commit()
            self.session.refresh(tag)
        
        return tag
    
    def link_author_affiliation(self, author_id: int, aff_id: int):
        """連結作者與機構"""
        link_exists = self.session.exec(
            select(AuthorAffiliationLink).where(
                AuthorAffiliationLink.author_id == author_id,
                AuthorAffiliationLink.affiliation_id == aff_id
            )
        ).first()
        
        if not link_exists:
            self.session.add(
                AuthorAffiliationLink(author_id=author_id, affiliation_id=aff_id)
            )
            self.session.commit()
    
    def update_tag_count_snapshot(self, tag_id: int, increment: int):
        """更新標籤計數快照"""
        snapshot = self.session.get(TagCountSnapshot, tag_id)
        
        if snapshot:
            snapshot.count += increment
            snapshot.last_updated = datetime.utcnow()
            self.session.add(snapshot)
        elif increment > 0:
            snapshot = TagCountSnapshot(
                tag_id=tag_id,
                count=increment,
                last_updated=datetime.utcnow()
            )
            self.session.add(snapshot)
        
        self.session.commit()
    
    def clear_paper_relations(self, paper_id: int):
        """清除論文的所有關聯"""
        # 獲取舊標籤並更新計數
        old_tags = self.session.exec(
            select(PaperTag.tag_id).where(PaperTag.paper_id == paper_id)
        ).all()
        
        # 刪除關聯
        self.session.exec(delete(PaperTag).where(PaperTag.paper_id == paper_id))
        self.session.exec(
            delete(PaperAuthorLink).where(PaperAuthorLink.paper_id == paper_id)
        )
        self.session.commit()
        
        # 更新標籤計數
        for tag_id in old_tags:
            self.update_tag_count_snapshot(tag_id, -1)
    
    def process_paper_authors(self, form, paper_id: int):
        """處理論文作者資訊"""
        idx = 0
        while True:
            author_name = form.get(f"author_name_{idx}")
            if not author_name or not author_name.strip():
                break
            
            try:
                author = self.get_or_create_author(author_name)
                self.session.add(
                    PaperAuthorLink(paper_id=paper_id, author_id=author.id)
                )
                
                # 處理機構
                affiliations_str = form.get(f"author_affiliations_{idx}", "")
                for aff_name in [x.strip() for x in affiliations_str.split(",") if x.strip()]:
                    aff = self.get_or_create_affiliation(aff_name)
                    self.link_author_affiliation(author.id, aff.id)
                
                self.session.commit()
            except Exception as e:
                print(f"處理作者 {author_name} 時出錯: {e}")
                self.session.rollback()
            
            idx += 1
    
    def process_paper_tags(self, tags_str: str, paper_id: int):
        """處理論文標籤"""
        if not tags_str or not tags_str.strip():
            return
        
        for tag_name in [x.strip() for x in tags_str.split(",") if x.strip()]:
            try:
                tag = self.get_or_create_tag(tag_name)
                
                # 檢查是否已存在連結
                link_exists = self.session.exec(
                    select(PaperTag).where(
                        PaperTag.paper_id == paper_id,
                        PaperTag.tag_id == tag.id
                    )
                ).first()
                
                if not link_exists:
                    self.session.add(PaperTag(paper_id=paper_id, tag_id=tag.id))
                    self.session.commit()
                    self.update_tag_count_snapshot(tag.id, 1)
            except Exception as e:
                print(f"處理標籤 {tag_name} 時出錯: {e}")
                self.session.rollback()
    
    def create_or_update_paper(
        self, 
        form, 
        paper_id: Optional[int] = None
    ) -> int:
        """創建或更新論文
        
        Args:
            form: 表單資料
            paper_id: 論文 ID（更新時使用）
            
        Returns:
            論文 ID
        """
        # 修正：確保 paper_id 是有效的整數才去查詢
        paper = None
        if paper_id and isinstance(paper_id, int) and paper_id > 0:
            paper = self.session.get(Paper, paper_id)
        
        # 如果找不到現有論文，創建新的
        if not paper:
            paper = Paper()
        
        # 更新論文資訊
        paper.paper_title = form.get("paper_title")
        paper.published_year = safe_int(form.get("published_year"))
        paper.published_month = safe_int(form.get("published_month"))
        paper.journal_or_conference = form.get("journal_or_conference", "")
        
        self.session.add(paper)
        self.session.commit()
        self.session.refresh(paper)
        
        # 如果是更新，先清除舊關聯
        if paper_id and isinstance(paper_id, int) and paper_id > 0:
            self.clear_paper_relations(paper.id)
        
        # 處理作者和標籤
        self.process_paper_authors(form, paper.id)
        self.process_paper_tags(form.get("tags", ""), paper.id)
        
        return paper.id