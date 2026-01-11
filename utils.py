from repeating_event_config_model import RepeatingEventConfig
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

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
  
def isRepeatingOnDay(repeating_event_config: RepeatingEventConfig, target_date: date) -> bool:
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