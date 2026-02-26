from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, AliasChoices

class EventIndexModel(BaseModel):
  model_config = ConfigDict(populate_by_name=True)
  id: str = Field(validation_alias=AliasChoices("eventId", "id"))
  userId: str
  description: Optional[str] = Field(default="", validation_alias=AliasChoices("title", "description"))
  startDate: datetime
  endDate: datetime
    
    
class EventModel(EventIndexModel):
  model_config = ConfigDict(populate_by_name=True)
  allDay: Optional[bool] = False
  content: Optional[dict] = None
  done: Optional[bool] = False
  fixed: Optional[bool] = False
  habitId: Optional[str] = None
  linkId: Optional[str] = None
  originalEventId: Optional[str] = None
  notifications: Optional[List[dict]] = Field(default_factory=list)
  priority: Optional[str] = None
  type: Optional[str] = Field(default="personal", validation_alias=AliasChoices("type", "eventType"))