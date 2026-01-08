from __future__ import annotations
import re
from datetime import date
from typing import List, Optional, Sequence
from pydantic import BaseModel, Field, field_validator

FREQ_RE = re.compile(r"^\d+(D|W|M(\d+)?|Y)$")

class RepeatingEventConfig(BaseModel):
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
    