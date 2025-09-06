from typing import List, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field, constr


Category = constr(strip_whitespace=True, min_length=2, max_length=32)


class PinCreate(BaseModel):
    kind: Literal["need", "offer"]
    categories: List[Category] = Field(min_length=1, max_length=5)
    title: Optional[constr(max_length=80)] = None
    body: constr(min_length=1, max_length=240)
    lat: float
    lng: float
    author_anon_id: constr(min_length=3, max_length=40)
    urgency: int = Field(2, ge=1, le=3)


class PinOut(BaseModel):
    id: str
    kind: str
    categories: List[str]
    title: Optional[str]
    body: str
    lat: float
    lng: float
    urgency: int
    author_anon_id: str
    created_at: datetime
    expires_at: datetime
    distance_mi: Optional[float] = None


class CommentCreate(BaseModel):
    body: constr(min_length=1, max_length=200)
    author_anon_id: constr(min_length=3, max_length=40)


class CommentOut(BaseModel):
    id: str
    pin_id: str
    body: str
    created_at: datetime


