"""
驗證與輔助函數 - 增強版
"""

def safe_int(value, default=0) -> int:
    """安全地將值轉換為整數"""
    if value is None or value == '':
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def safe_str(value, default="") -> str:
    """安全地將值轉換為字串"""
    if value is None:
        return default
    return str(value).strip()

def is_valid_id(value) -> bool:
    """檢查是否為有效的 ID
    
    有效的 ID 必須：
    1. 不為 None
    2. 可以轉換為整數
    3. 大於 0
    """
    if value is None or value == '':
        return False
    try:
        id_val = int(str(value).strip())
        return id_val > 0
    except (ValueError, TypeError):
        return False

def validate_required_field(value, field_name: str) -> str:
    """驗證必填欄位
    
    Args:
        value: 欄位值
        field_name: 欄位名稱
        
    Returns:
        清理後的字串值
        
    Raises:
        ValueError: 當欄位為空時
    """
    cleaned_value = safe_str(value)
    if not cleaned_value:
        raise ValueError(f"{field_name} 不能為空")
    return cleaned_value