from __future__ import annotations
import re
from datetime import date
from typing import List, Optional, Sequence
from pydantic import BaseModel, Field, field_validator, ConfigDict, AliasChoices
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FREQ_RE = re.compile(r"^\d+(D|W|M(\d+)?|Y)$")

class StartTime(BaseModel):
  hour: int = Field(..., ge=0, le=23)
  minute: int = Field(..., ge=0, le=59)
  timezone: str

  @field_validator("timezone")
  @classmethod
  def validate_timezone(cls, v: str) -> str:
      # Validate IANA tz database names like "America/New_York"
      try:
          ZoneInfo(v)
      except ZoneInfoNotFoundError as e:
          raise ValueError(f"Invalid timezone: {v}") from e
      return v

class HabitIndexModel(BaseModel):
  model_config = ConfigDict(populate_by_name=True)
  id: str = Field(validation_alias=AliasChoices("habitId", "id"))
  userId: str
  name: str = Field(validation_alias=AliasChoices("title", "name"))
  creationDate: date
  frequency: str = Field(..., description="e.g. '1D', '2W', '1M', '1M3' (every month on 3rd occurence of a specific day), '1Y'")
  days: List[str] = Field(
    default_factory=list, 
    description="Can be a list of days for weekly frequency, e.g. ['Mon', 'Wed', 'Fri'], \
      a day of a month for monthly frequency, e.g. ['15'], \
      a month and day for yearly frequency, e.g. ['Jan 15'], \
      and a day of week for monthly frequency with occurrence, e.g. ['1M2'] ['Mon'] for second Monday of the month."
  )
  exceptionDates: Optional[List[date]] = None
  stopDate: Optional[date] = None
  startTime: StartTime
  length: int = Field(..., gt=0, description="Event length in minutes")
  
  @field_validator("frequency")
  @classmethod
  def validate_frequency(cls, v: str) -> str:
      if not FREQ_RE.match(v):
          raise ValueError("Invalid frequency format (expected like 1D, 2W, 1M, 1M3, 1Y)")
      return v

  @field_validator("days")
  @classmethod
  def coerce_days_to_strings(cls, v: Sequence[object]) -> List[str]:
      # Ensures even numeric inputs become strings ("15" not 15)
      return [str(x) for x in v]
    
    
class RepeatingEventConfigModel(HabitIndexModel):
    model_config = ConfigDict(populate_by_name=True)
    allDay: bool = False
    content: Optional[dict] = None
    fixed: bool = False
    notifications: Optional[List[dict]] = Field(default_factory=list)
    prevVersionHabitId: Optional[str] = None
    priority: Optional[str] = None
    eventType: Optional[str] = Field(default="personal", validation_alias=AliasChoices("type", "eventType"))