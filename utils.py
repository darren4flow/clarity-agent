from repeating_event_config_model import HabitIndexModel
from datetime import date, datetime, timedelta
from typing import Optional
from decimal import Decimal
from enum import Enum
from uuid import UUID
import logging

# Configure logging
logger = logging.getLogger(__name__)

def pprint_date(d: date, time: str = "") -> str:
    if time:
        return d.strftime(f"%b %d, %Y at {time}")
    return d.strftime("%b %d, %Y")

def get_complete_weeks_between_dates(d1: date, d2: date) -> int:
    return abs((d1 - d2).days) // 7
  
def get_day_of_week(d: date) -> str:
    # JS Date.getDay(): Sun..Sat
    days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    return days[(d.weekday() + 1) % 7]
  
def format_yearly_date(d: date) -> str:
    month_abbr = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{month_abbr[d.month - 1]} {d.day}"
  
def get_weekday_occurrence(d: date) -> int:
    # 1..5 occurrence of that weekday within the month
    return ((d.day - 1) // 7) + 1
  
def months_between(d1: date, d2: date) -> int:
    # More correct than the JS version: includes year difference
    return abs((d2.year - d1.year) * 12 + (d2.month - d1.month))
  
def isRepeatingOnDay(repeating_event_config: HabitIndexModel, target_date: date) -> bool:
  creation_date = repeating_event_config.creationDate
  frequency = repeating_event_config.frequency
  
  fits_frequency = True
  is_scheduled_for_this_date = False
  
  if "D" in frequency:
    daily_frequency = int(frequency[:-1])
    days_between = abs((target_date - creation_date).days)
    fits_frequency = (days_between % daily_frequency) == 0
    if fits_frequency:
      is_scheduled_for_this_date = True
      
  elif "W" in frequency:
    weekly_frequency = int(frequency[:-1])
    complete_weeks_between = get_complete_weeks_between_dates(creation_date, target_date)
    fits_frequency = (complete_weeks_between % weekly_frequency) == 0
    if fits_frequency:
      is_scheduled_for_this_date = get_day_of_week(target_date) in repeating_event_config.days
  
  elif "M" in frequency:
    if frequency.endswith("M"):
      monthly_frequency = int(frequency[:-1])
      months_diff = months_between(creation_date, target_date)
      fits_frequency = (months_diff % monthly_frequency) == 0
      if fits_frequency:
        is_scheduled_for_this_date = str(target_date.day) in repeating_event_config.days
    else:
      monthly_frequency_str, occurrence_condition_str = frequency.split("M")
      monthly_frequency = int(monthly_frequency_str)
      occurrence_condition = int(occurrence_condition_str)
      months_diff = months_between(creation_date, target_date)
      months_fits_frequency = (months_diff % monthly_frequency) == 0
      weekday_occurrence_condition = (
        get_day_of_week(target_date) in repeating_event_config.days 
        and get_weekday_occurrence(target_date) == occurrence_condition
      )
      fits_frequency = months_fits_frequency and weekday_occurrence_condition
      is_scheduled_for_this_date = fits_frequency
  elif "Y" in frequency:
    yearly_frequency = int(frequency[:-1])
    years_between = abs(target_date.year - creation_date.year)
    fits_frequency = (years_between % yearly_frequency) == 0
    if fits_frequency:
      is_scheduled_for_this_date = format_yearly_date(target_date) in repeating_event_config.days
      
  no_exception_for_this_date = True
  if repeating_event_config.exceptionDates:
    no_exception_for_this_date = target_date not in repeating_event_config.exceptionDates
  on_or_after_creation_date = target_date >= creation_date
  not_on_or_after_stop_date = True
  if repeating_event_config.stopDate:
    not_on_or_after_stop_date = target_date < repeating_event_config.stopDate
    
  return (
      fits_frequency
      and is_scheduled_for_this_date
      and no_exception_for_this_date
      and not_on_or_after_stop_date
      and on_or_after_creation_date
  )
  
  
  
def _to_dynamodb_compatible(value):
    """
    Recursively convert common non-DynamoDB-native Python types to
    DynamoDB-friendly primitives for boto3.dynamodb.types.TypeSerializer.

    Fixes: TypeError: Unsupported type "<class 'datetime.date'>"
    """
    if value is None:
        return None

    # bool is a subclass of int; handle before numeric checks
    if isinstance(value, bool):
        return value

    # Dates/times -> ISO string
    if isinstance(value, (date, datetime)):
        return value.isoformat()

    # DynamoDB does not support float; prefer Decimal
    if isinstance(value, float):
        return Decimal(str(value))

    # Common "stringable" types
    if isinstance(value, (UUID, Enum)):
        return str(value)

    # Recurse containers
    if isinstance(value, dict):
        return {str(k): _to_dynamodb_compatible(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [_to_dynamodb_compatible(v) for v in value]

    if isinstance(value, set):
        # DynamoDB supports sets, but TypeSerializer requires set of uniform primitives.
        # Converting to list is safest unless you specifically need DynamoDB sets.
        return [_to_dynamodb_compatible(v) for v in value]

    return value
  
  
  
def time_unit_map(time_unit: str) -> str:
    mapping = {
      "daily": "D",
      "weekly": "W",
      "monthly": "M",
      "yearly": "Y"
    }
    return mapping.get(time_unit, "D")


# def get_new_end_datetime(
#     current_length: int,
#     new_length_minutes: Optional[int],
#     new_end_datetime_str: Optional[str],
#     current_start_datetime: datetime,
#     new_start_datetime: Optional[datetime],
# ) -> Optional[datetime]:
#     if new_end_datetime_str is not None:
#         try:
#             return datetime.fromisoformat(new_end_datetime_str)
#         except ValueError:
#             raise ValueError(f"invalid ISO datetime: {new_end_datetime_str}")

#     if new_length_minutes is not None:
#         if new_length_minutes < 0:
#             raise ValueError("new_length_minutes must be >= 0")
#         start = new_start_datetime or current_start_datetime
#         return (start + timedelta(minutes=new_length_minutes)) if start is not None else None

#     # current_length is required (int) — allow 0
#     if current_length < 0:
#         raise ValueError("current_length must be >= 0")
#     start = new_start_datetime or current_start_datetime
#     return (start + timedelta(minutes=current_length)) if start is not None else None



"""
- unique event being moved to a new time (no date provided)
- unque event moved to a new date (no time provided)
- unique event moved to a new date and time
- unique All-Day event 

"""
def get_new_end_datetime(
    current_length: int,
    current_start_datetime: datetime,
    current_end_datetime: datetime,
    new_start_date: Optional[date] = None,
    new_start_time_str: Optional[str] = None,
    new_end_date: Optional[date] = None,
    new_end_time_str: Optional[str] = None,
    new_length_minutes: Optional[int] = None
) -> Optional[datetime]:
    if new_start_date is not None:
        # Moving to a new date (all-day event)
        new_start_datetime = current_start_datetime.replace(
            year=new_start_date.year,
            month=new_start_date.month,
            day=new_start_date.day
        )
        if new_start_time_str is not None:
            # Also moving to a new time on that date
            new_start_time = datetime.strptime(new_start_time_str, "%H:%M").time()
            new_start_datetime = new_start_datetime.replace(
                hour=new_start_time.hour,
                minute=new_start_time.minute,
                second=0,
                microsecond=0
            )
        if new_end_date is not None:
            # New end date specified
            new_end_datetime = current_end_datetime.replace(
                year=new_end_date.year,
                month=new_end_date.month,
                day=new_end_date.day
            )
            if new_end_time_str is not None:
                # New end time specified
                new_end_time = datetime.strptime(new_end_time_str, "%H:%M").time()
                new_end_datetime = new_end_datetime.replace(
                    hour=new_end_time.hour,
                    minute=new_end_time.minute,
                    second=0,
                    microsecond=0
                )
            elif new_length_minutes is not None and new_end_time_str is None and new_start_time_str is None:
                error_msg = """The new start date and new end date were provided with a new length. Either just provide the new length without an end date. Or provide both an end date and end time."""
                logger.warning(error_msg)
                raise Exception(error_msg)
            elif new_length_minutes is not None and new_start_time_str is not None:
                error_msg = """The new start date, start time, and end date were provided with a new length. Either just provide the new length without an end date. Or provide both an end date and end time."""
                logger.warning(error_msg)
                raise Exception(error_msg)
            elif new_length_minutes is None and new_start_time_str is not None: 
                error_msg = """The new start date, startTime, and endDate were provided. The endDate needs an endTime to make sense. Or use a new length without an end date."""
                logger.warning(error_msg)
                raise Exception(error_msg)
            if new_end_datetime < new_start_datetime:
                logger.warning("New end datetime is earlier than new start datetime.")
                return None    
            
            return new_end_datetime    
        
        if new_end_time_str is not None:
            # New end time specified
            new_end_time = datetime.strptime(new_end_time_str, "%H:%M").time()
            new_end_datetime = new_start_datetime.replace(
                hour=new_end_time.hour,
                minute=new_end_time.minute,
                second=0,
                microsecond=0
            )
            if new_end_datetime < new_start_datetime:
                logger.warning("New end datetime is earlier than new start datetime.")
                return None
            return new_end_datetime
        if new_length_minutes is not None:
            new_end_datetime = new_start_datetime + timedelta(minutes=new_length_minutes)
            return new_end_datetime
        new_end_datetime = new_start_datetime + timedelta(minutes=current_length)
        return new_end_datetime
    elif new_start_time_str is not None:
        # Moving to a new time on the same date
        new_start_time = datetime.strptime(new_start_time_str, "%H:%M").time()
        new_start_datetime = current_start_datetime.replace(
            hour=new_start_time.hour,
            minute=new_start_time.minute,
            second=0,
            microsecond=0
        )
        
        if new_end_date is not None:
            # New end date specified
            new_end_datetime = current_end_datetime.replace(
                year=new_end_date.year,
                month=new_end_date.month,
                day=new_end_date.day
            )
            if new_end_time_str is not None:
                # New end time specified
                new_end_time = datetime.strptime(new_end_time_str, "%H:%M").time()
                new_end_datetime = new_end_datetime.replace(
                    hour=new_end_time.hour,
                    minute=new_end_time.minute,
                    second=0,
                    microsecond=0
                )
            else: 
                error_msg = "The new start time and new end date were provided without a new end time."
                logger.error(error_msg)
                raise Exception(error_msg)
            if new_end_datetime < new_start_datetime:
                logger.warning("New end datetime is earlier than new start datetime.")
                return None
            return new_end_datetime
        
        if new_end_time_str is not None:
            # New end time specified
            new_end_time = datetime.strptime(new_end_time_str, "%H:%M").time()
            new_end_datetime = new_start_datetime.replace(
                hour=new_end_time.hour,
                minute=new_end_time.minute,
                second=0,
                microsecond=0
            )
            if new_end_datetime < new_start_datetime:
                logger.warning("New end datetime is earlier than new start datetime.")
                return None
            return new_end_datetime
        if new_length_minutes is not None:
            new_end_datetime = new_start_datetime + timedelta(minutes=new_length_minutes)
            return new_end_datetime
        new_end_datetime = new_start_datetime + timedelta(minutes=current_length)
        return new_end_datetime
    elif new_end_date is not None:
        # Moving to a new end date (all-day event)
        new_end_datetime = current_end_datetime.replace(
            year=new_end_date.year,
            month=new_end_date.month,
            day=new_end_date.day
        )
        if new_end_time_str is not None:
            # Also moving to a new end time on that date
            new_end_time = datetime.strptime(new_end_time_str, "%H:%M").time()
            new_end_datetime = new_end_datetime.replace(
                hour=new_end_time.hour,
                minute=new_end_time.minute,
                second=0,
                microsecond=0
            )
        elif new_length_minutes:
            new_end_datetime = new_end_datetime.replace(
                hour=current_start_datetime.hour,
                minute=current_start_datetime.minute,
            ) + timedelta(minutes=new_length_minutes)
        if new_end_datetime < current_start_datetime:
            logger.warning("New end datetime is earlier than current start datetime.")
            return None    
        
        return new_end_datetime    
    elif new_end_time_str is not None:
        # Moving to a new end time on the same date
        new_end_time = datetime.strptime(new_end_time_str, "%H:%M").time()
        new_end_datetime = current_end_datetime.replace(
            hour=new_end_time.hour,
            minute=new_end_time.minute,
            second=0,
            microsecond=0
        )
        if new_end_datetime < current_start_datetime:
            logger.warning("New end datetime is earlier than current start datetime.")
            return None    
        
        return new_end_datetime
    elif new_length_minutes is not None:
        # No date change; just length change
        if new_length_minutes < 0:
            logger.warning("new_length_minutes must be >= 0")
            return None
        start = current_start_datetime
        return start + timedelta(minutes=new_length_minutes)
    else:
        # No date change; return current end datetime
        return current_end_datetime