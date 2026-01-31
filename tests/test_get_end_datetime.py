import sys
from pathlib import Path
from xxlimited import new
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import pytest
from unittest.mock import Mock
from types import SimpleNamespace
import s2s_session_manager
from s2s_session_manager import S2sSessionManager
import utils
from utils import get_new_end_datetime
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

def test_repeating_all_day_move_to_new_date_preserve_end_time():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=2)).date()
  
  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_date)
  expected_end_datetime = current_end_datetime.replace(
      year=new_start_date.year,
      month=new_start_date.month,
      day=new_start_date.day
  )
  assert res == expected_end_datetime
  
  
  
"""
Test cases for converting repeating all day events to non-all day events on a different date and time
"""
def test_convert_repeating_all_day_event_to_different_date_with_start_time():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=2)).date()
  new_start_time = "15:00"
  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_date, new_start_time)
  expected_end_datetime = current_start_datetime.replace(
      year=new_start_date.year,
      month=new_start_date.month,
      day=new_start_date.day,
      hour=15,
      minute=30,
      second=0,
      microsecond=0
  )
  assert res == expected_end_datetime
  
def test_convert_repeating_all_day_event_to_different_date_with_start_time_and_new_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_length_minutes = 90
  new_start_date = (current_start_datetime + timedelta(days=2)).date()
  new_start_time = "15:00"
  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_date, new_start_time, new_length_minutes=new_length_minutes)
  expected_end_datetime = current_start_datetime.replace(
      year=new_start_date.year,
      month=new_start_date.month,
      day=new_start_date.day,
      hour=16,
      minute=30,
      second=0,
      microsecond=0
  )
  assert res == expected_end_datetime
  
  
def test_convert_repeating_all_day_event_to_different_date_with_start_time_and_end_time():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=2)).date()
  new_start_time = "15:00"
  new_end_time = "16:30"
  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_date, new_start_time, new_end_time_str=new_end_time)
  expected_end_datetime = current_start_datetime.replace(
      year=new_start_date.year,
      month=new_start_date.month,
      day=new_start_date.day,
      hour=16,
      minute=30,
      second=0,
      microsecond=0
  )
  assert res == expected_end_datetime
  
  
def test_convert_repeating_all_day_event_to_different_date_with_start_time_and_end_datetime():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=2)).date()
  new_start_time = "15:00"
  new_end_date = (current_start_datetime + timedelta(days=3)).date()
  new_end_time = "16:30"
  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_date, new_start_time, new_end_date=new_end_date, new_end_time_str=new_end_time)
  expected_end_datetime = current_start_datetime.replace(
      year=new_end_date.year,
      month=new_end_date.month,
      day=new_end_date.day,
      hour=16,
      minute=30,
      second=0,
      microsecond=0
  )
  assert res == expected_end_datetime
  
  
  
  
"""
Test cases for converting repeating all day events to non-all day events on the same date but different time
"""
def test_convert_repeating_all_day_event_to_have_start_time_on_same_date():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_time = "15:00"
  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_time_str=new_start_time)
  expected_end_datetime = current_start_datetime.replace(
      hour=15,
      minute=30,
      second=0,
      microsecond=0
  )
  assert res == expected_end_datetime
  
def test_convert_repeating_all_day_event_to_have_start_time_on_same_date_with_new_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_time = "15:00"
  new_length_minutes = 90
  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_time_str=new_start_time, new_length_minutes=new_length_minutes)
  expected_end_datetime = current_start_datetime.replace(
      hour=16,
      minute=30,
      second=0,
      microsecond=0
  )
  assert res == expected_end_datetime
    
    
def test_convert_repeating_all_day_event_to_have_start_time_and_end_time_on_same_date():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_time = "15:00"
  new_end_time = "16:30"
  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_time_str=new_start_time, new_end_time_str=new_end_time)
  expected_end_datetime = current_start_datetime.replace(
      hour=16,
      minute=30,
      second=0,
      microsecond=0
  )
  assert res == expected_end_datetime
  
def test_convert_repeating_all_day_event_to_have_start_time_and_end_datetime_on_same_date():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_time = "15:00"
  new_end_date = (current_start_datetime + timedelta(days=1)).date()
  new_end_time = "16:30"
  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_time_str=new_start_time, new_end_date=new_end_date, new_end_time_str=new_end_time)
  expected_end_datetime = current_start_datetime.replace(
      year=new_end_date.year,
      month=new_end_date.month,
      day=new_end_date.day,
      hour=16,
      minute=30,
      second=0,
      microsecond=0
  )
  assert res == expected_end_datetime
  
  
  
  
  
def test_move_repeating_non_all_day_event_to_different_date():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=2)).date()

  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_date=new_start_date)
  expected_end_datetime = current_end_datetime.replace(
      year=new_start_date.year,
      month=new_start_date.month,
      day=new_start_date.day
  )
  assert res == expected_end_datetime

def test_move_repeating_non_all_day_event_to_different_date_with_new_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=2)).date()
  new_length_minutes = 90

  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_date=new_start_date, new_length_minutes=new_length_minutes)
  expected_end_datetime = current_end_datetime.replace(
      year=new_start_date.year,
      month=new_start_date.month,
      day=new_start_date.day
  ) + timedelta(minutes=(new_length_minutes - current_length))
  assert res == expected_end_datetime

def test_move_repeating_non_all_day_event_to_different_start_date_and_start_time():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=2)).date()
  new_start_time = "15:00"
  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_date=new_start_date, new_start_time_str=new_start_time)
  expected_end_datetime = current_end_datetime.replace(
      year=new_start_date.year,
      month=new_start_date.month,
      day=new_start_date.day,
      hour=15,
      minute=30,
      second=0,
      microsecond=0
  )
  assert res == expected_end_datetime

def test_move_repeating_non_all_day_event_to_different_date_and_time_with_new_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=2)).date()
  new_start_time = "15:00"
  new_length_minutes = 90

  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_date=new_start_date, new_start_time_str=new_start_time, new_length_minutes=new_length_minutes)
  expected_end_datetime = current_start_datetime.replace(
      year=new_start_date.year,
      month=new_start_date.month,
      day=new_start_date.day,
      hour=16,
      minute=30,
      second=0,
      microsecond=0
  )
  assert res == expected_end_datetime

def test_move_repeating_non_all_day_event_to_different_time_on_same_date():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_time = "15:00"

  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_time_str=new_start_time)
  expected_end_datetime = current_start_datetime.replace(
      hour=15,
      minute=30,
      second=0,
      microsecond=0
  )
  assert res == expected_end_datetime

def test_move_repeating_non_all_day_event_to_different_time_on_same_date_with_new_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_time = "15:00"
  new_length_minutes = 90

  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_time_str=new_start_time, new_length_minutes=new_length_minutes)
  expected_end_datetime = current_start_datetime.replace(
      hour=16,
      minute=30,
      second=0,
      microsecond=0
  )
  assert res == expected_end_datetime

    
    
    
    
    
    
    
    
    
  
def test_move_unique_all_day_event_to_different_date():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=5)).date()

  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_date=new_start_date)
  expected_end_datetime = current_end_datetime.replace(
      year=new_start_date.year,
      month=new_start_date.month,
      day=new_start_date.day
  )
  assert res == expected_end_datetime



def test_move_unique_all_day_event_to_time_on_same_date():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_time = "09:00"

  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_time_str=new_start_time)
  expected_end_datetime = current_start_datetime.replace(
      hour=9,
      minute=30,
      second=0,
      microsecond=0
  )
  assert res == expected_end_datetime
    

def test_move_unique_all_day_event_to_time_on_different_date():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=3)).date()
  new_start_time = "09:00"

  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_date=new_start_date, new_start_time_str=new_start_time)
  expected_end_datetime = current_start_datetime.replace(
      year=new_start_date.year,
      month=new_start_date.month,
      day=new_start_date.day,
      hour=9,
      minute=30,
      second=0,
      microsecond=0
  )
  assert res == expected_end_datetime
  
  
  """
  NEw test cases will be added here
  """
  
def test_unchanged():
  pass
  
def test_changing_length():
  pass

def rest_changing_startDate():
  pass

def test_changing_startTime():
  pass

def test_changing_endDate():
  pass

def test_changing_endTime():
  pass

def test_changing_startDate_length():
  pass

def test_changing_startTime_length():
  pass

def test_changing_endDate_length():
  pass

def test_changing_endTime_length():
  pass

def test_changing_startDate_startTime():
  pass

def test_changing_startDate_endDate():
  pass

def test_changing_startDate_endTime():
  pass

def test_changing_startTime_endDate():
  pass

def test_changing_startTime_endTime():
  pass

def test_changing_endDate_endTime():
  pass

def test_changing_startDate_startTime_length():
  pass

def test_changing_startDate_endDate_length():
  pass



def test_changing_startDate_endTime_length():
  pass

def test_changing_startTime_endDate_length():
  pass

def test_changing_startTime_endTime_length():
  pass

def test_changing_endDate_endTime_length():
  pass

def test_changing_startDate_startTime_endDate():
  pass

def test_changing_startDate_startTime_endTime():
  pass

def test_changing_startDate_endDate_endTime():
  pass

def test_changing_startTime_endDate_endTime():
  pass

def test_changing_startDate_startTime_endDate_length():
  pass

def test_changing_startDate_startTime_endTime_length():
  pass

def test_changing_startDate_endDate_endTime_length():
  pass

def test_changing_startTime_endDate_endTime_length():
  pass

def test_changing_startDate_startTime_endDate_endTime():
  pass

def test_changing_startDate_startTime_endDate_endTime_length():
  pass