# Pydantic schemas (optional)
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# ---------- Base ----------

class ORMModel(BaseModel):
    """Base with orm_mode for SQLAlchemy compatibility."""
    model_config = {"from_attributes": True}


# ---------- Assets ----------

class AssetOut(ORMModel):
    id: str
    report_id: str
    asset_type: str
    filename: str
    url: str
    metadata: Optional[dict] = None
    created_at: datetime


# ---------- Reports ----------

class ReportSummary(ORMModel):
    total_photos: int = 0
    critical_count: int = 0
    important_count: int = 0

class ReportSection(ORMModel):
    photo_index: int
    photo_filename: str
    thumbnail_url: Optional[str] = None
    original_url: Optional[str] = None
    location: Optional[str] = ""
    materials_description: Optional[str] = ""
    observations: List[str] = Field(default_factory=list)
    potential_issues: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    is_critical: bool = False
    is_important: bool = False

class ReportJSON(ORMModel):
    report_id: str
    property_id: str
    inspection_date: str
    sections: List[ReportSection]
    summary: ReportSummary

class ReportOut(ORMModel):
    id: str
    property_id: str
    inspection_date: datetime
    pdf_standard_url: Optional[str] = None
    pdf_hq_url: Optional[str] = None
    pdf_hq_expires_at: Optional[datetime] = None
    json_url: Optional[str] = None
    summary: Optional[str] = None
    critical_count: int = 0
    important_count: int = 0
    created_at: datetime
    assets: List[AssetOut] = Field(default_factory=list)


# ---------- Properties ----------

class PropertyOut(ORMModel):
    id: str
    client_id: str
    address: str
    property_type: Optional[str] = None
    details_json: Optional[dict] = None
    created_at: datetime


# ---------- Client Dashboard ----------

class LatestReportLite(ORMModel):
    id: str
    inspection_date: datetime
    critical_count: int
    important_count: int

class PropertyWithLatest(ORMModel):
    id: str
    address: str
    property_type: Optional[str] = None
    latest_report: Optional[LatestReportLite] = None

class ClientInfo(ORMModel):
    id: str
    company_name: Optional[str] = None
    contact_name: Optional[str] = None

class ClientDashboard(ORMModel):
    client: ClientInfo
    properties: List[PropertyWithLatest]


# ---------- Common payloads ----------

class UploadReportResponse(ORMModel):
    message: str = "Report upload initiated"
    report_id: str
    status: str = "processing"

class PDFUrls(BaseModel):
    standard: Optional[str] = None
    highquality: Optional[str] = None

class ReportDetailsResponse(BaseModel):
    report: ReportJSON
    pdf_urls: PDFUrls
    property: dict
