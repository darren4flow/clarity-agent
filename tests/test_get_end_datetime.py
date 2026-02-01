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


"""
  NEw test cases will be added here
"""
def test_unchanged():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes

  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime)
  assert res == current_end_datetime
  
  
def test_changing_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_length_minutes = 90

  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_length_minutes=new_length_minutes)
  expected_end_datetime = current_start_datetime + timedelta(minutes=new_length_minutes)
  assert res == expected_end_datetime


"""
If All Day, then the date is just moved.
If it's not all day, then the time is preserved. The user should have said if they want it to be become an all day event in this case.
"""
def test_changing_startDate():
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


"""
If it was an All Day, then it should become non-all day with the new time.
If it was not an All Day, then the date is preserved and only the time is changed
"""
def test_changing_startTime():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_time = "15:00"

  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_time_str=new_start_time)
  expected_end_datetime = current_end_datetime.replace(
      year=current_start_datetime.year,
      month=current_start_datetime.month,
      day=current_start_datetime.day, 
      hour=15, 
      minute=30, 
      second=0, 
      microsecond=0
  )
  assert res == expected_end_datetime

#TODO
"""
If it was an All Day, then it should remain an all day with the new end date.
If it was not an All Day,
"""
def test_changing_endDate():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_end_date = (current_start_datetime + timedelta(days=2)).date()

  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_end_date=new_end_date)
  expected_end_datetime = current_end_datetime.replace(
      year=new_end_date.year,
      month=new_end_date.month,
      day=new_end_date.day
  )
  assert res == expected_end_datetime

#TODO
"""
If it was an All Day, then it will become a timed event, but it should have a defined start time as 
If it was not an All Day, then the date is preserved and only the end time is changed
"""
def test_changing_endTime():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_end_time_str = "15:00"

  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_end_time_str=new_end_time_str)
  expected_end_datetime = current_end_datetime.replace(
      year=current_start_datetime.year,
      month=current_start_datetime.month,
      day=current_start_datetime.day,
      hour=15, 
      minute=0, 
      second=0, 
      microsecond=0
  )
  assert res == expected_end_datetime


def test_changing_startDate_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=2)).date()
  new_length_minutes = 90

  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_date=new_start_date, new_length_minutes=new_length_minutes)
  expected_end_datetime = current_start_datetime.replace(
      year=new_start_date.year,
      month=new_start_date.month,
      day=new_start_date.day
  ) + timedelta(minutes=new_length_minutes)
  assert res == expected_end_datetime

def test_changing_startTime_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_time = "15:00"
  new_length_minutes = 90

  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_start_time_str=new_start_time, new_length_minutes=new_length_minutes)
  expected_end_datetime = current_start_datetime.replace(
      hour=15,
      minute=0,
      second=0,
      microsecond=0
  ) + timedelta(minutes=new_length_minutes)
  assert res == expected_end_datetime


def test_changing_endDate_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_end_date = (current_start_datetime + timedelta(days=2)).date()
  new_length_minutes = 90

  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_end_date=new_end_date, new_length_minutes=new_length_minutes)
  expected_end_datetime = current_start_datetime.replace(
      year=new_end_date.year,
      month=new_end_date.month,
      day=new_end_date.day,
      hour=current_start_datetime.hour,
      minute=current_start_datetime.minute,
      second=0,
      microsecond=0
  ) + timedelta(minutes=new_length_minutes)
  assert res == expected_end_datetime

def test_changing_endTime_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_end_time = "15:00"
  new_length_minutes = 999

  res = get_new_end_datetime(current_length, current_start_datetime, current_end_datetime, new_end_time_str=new_end_time, new_length_minutes=new_length_minutes)
  expected_end_datetime = current_end_datetime.replace(hour=15, minute=0)
  assert res == expected_end_datetime

def test_changing_startDate_startTime():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=2)).date()
  new_start_time = "15:00"

  res = get_new_end_datetime(
    current_length, 
    current_start_datetime, 
    current_end_datetime, 
    new_start_date=new_start_date, 
    new_start_time_str=new_start_time
  )
  expected_end_datetime = current_start_datetime.replace(
    year=new_start_date.year,
    month=new_start_date.month,
    day=new_start_date.day,
    hour=15, 
    minute=30
  )
  assert res == expected_end_datetime

def test_changing_startDate_endDate():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=2)).date()
  new_end_date = (current_end_datetime + timedelta(days=3)).date()

  res = get_new_end_datetime(
    current_length, 
    current_start_datetime, 
    current_end_datetime, 
    new_start_date=new_start_date, 
    new_end_date=new_end_date
  )
  expected_end_datetime = current_end_datetime.replace(
    year=new_end_date.year,
    month=new_end_date.month,
    day=new_end_date.day
  )
  assert res == expected_end_datetime


def test_changing_startDate_endTime():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=1)).date()
  new_end_time_str = "15:00"

  res = get_new_end_datetime(
    current_length, 
    current_start_datetime, 
    current_end_datetime, 
    new_start_date=new_start_date, 
    new_end_time_str=new_end_time_str
  )
  expected_end_datetime = current_end_datetime.replace(
    year=new_start_date.year,
    month=new_start_date.month,
    day=new_start_date.day,
    hour=15,
    minute=0
  )
  assert res == expected_end_datetime


def test_changing_startTime_endDate():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_time_str = "15:00"
  new_end_date = (current_start_datetime + timedelta(days=1)).date()

  with pytest.raises(Exception) as excinfo:
    get_new_end_datetime(
      current_length, 
      current_start_datetime, 
      current_end_datetime, 
      new_start_time_str=new_start_time_str, 
      new_end_date=new_end_date,
    )

  error_msg = "Invalid parameter combination: new_end_date provided without new_end_time_str while new_start_time_str is set."
  assert error_msg == str(excinfo.value)

def test_changing_startTime_endTime():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_time_str = "15:00"
  new_end_time_str = "16:00"

  res = get_new_end_datetime(
    current_length, 
    current_start_datetime, 
    current_end_datetime, 
    new_start_time_str=new_start_time_str, 
    new_end_time_str=new_end_time_str
  )
  expected_end_datetime = current_end_datetime.replace(
    hour=16,
    minute=0
  )
  assert res == expected_end_datetime

def test_changing_endDate_endTime():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_end_date = (current_start_datetime + timedelta(days=2)).date()
  new_end_time_str = "16:00"

  res = get_new_end_datetime(
    current_length, 
    current_start_datetime, 
    current_end_datetime, 
    new_end_date=new_end_date, 
    new_end_time_str=new_end_time_str
  )
  expected_end_datetime = current_end_datetime.replace(
    year=new_end_date.year,
    month=new_end_date.month,
    day=new_end_date.day,
    hour=16,
    minute=0
  )
  assert res == expected_end_datetime

def test_changing_startDate_startTime_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=2)).date()
  new_start_time_str = "16:00"
  new_length_minutes = 60

  res = get_new_end_datetime(
    current_length, 
    current_start_datetime, 
    current_end_datetime, 
    new_start_date=new_start_date, 
    new_start_time_str=new_start_time_str,
    new_length_minutes=new_length_minutes
  )
  expected_end_datetime = current_end_datetime.replace(
    year=new_start_date.year,
    month=new_start_date.month,
    day=new_start_date.day,
    hour=17,
    minute=0
  )
  assert res == expected_end_datetime


def test_changing_startDate_endDate_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=1)).date()
  new_end_date = (current_start_datetime + timedelta(days=2)).date()
  new_length_minutes = 60

  with pytest.raises(Exception) as excinfo:
    get_new_end_datetime(
      current_length, 
      current_start_datetime, 
      current_end_datetime, 
      new_start_date=new_start_date, 
      new_end_date=new_end_date,
      new_length_minutes=new_length_minutes
    )

  error_msg = "Invalid parameter combination: new_end_date and new_length_minutes provided without new_end_time_str."
  assert error_msg == str(excinfo.value)


def test_changing_startDate_endTime_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=1)).date()
  new_end_time_str = "16:00"
  new_length_minutes = 60

  res = get_new_end_datetime(
    current_length, 
    current_start_datetime, 
    current_end_datetime, 
    new_start_date=new_start_date, 
    new_end_time_str=new_end_time_str,
    new_length_minutes=new_length_minutes
  )
  expected_end_datetime = current_end_datetime.replace(
    year=new_start_date.year,
    month=new_start_date.month,
    day=new_start_date.day,
    hour=16,
    minute=0
  )
  assert res == expected_end_datetime

def test_changing_startTime_endDate_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_time_str = "16:00"
  new_end_date = (current_start_datetime + timedelta(days=1)).date()
  new_length_minutes = 60

  with pytest.raises(Exception) as excinfo:
    get_new_end_datetime(
      current_length, 
      current_start_datetime, 
      current_end_datetime, 
      new_start_time_str=new_start_time_str, 
      new_end_date=new_end_date,
      new_length_minutes=new_length_minutes
    )

  error_msg = "Invalid parameter combination: new_end_date provided without new_end_time_str while new_start_time_str is set."
  assert error_msg == str(excinfo.value)

def test_changing_startTime_endTime_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_time_str = "15:00"
  new_end_time_str = "16:00"
  new_length_minutes = 999

  res = get_new_end_datetime(
    current_length, 
    current_start_datetime, 
    current_end_datetime, 
    new_start_time_str=new_start_time_str, 
    new_end_time_str=new_end_time_str,
    new_length_minutes=new_length_minutes
  )
  expected_end_datetime = current_end_datetime.replace(
    hour=16,
    minute=0
  )
  assert res == expected_end_datetime

def test_changing_endDate_endTime_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_end_date = (current_start_datetime + timedelta(days=1)).date()
  new_end_time_str = "16:00"
  new_length_minutes = 999

  res = get_new_end_datetime(
    current_length, 
    current_start_datetime, 
    current_end_datetime, 
    new_end_date=new_end_date, 
    new_end_time_str=new_end_time_str,
    new_length_minutes=new_length_minutes
  )
  expected_end_datetime = current_end_datetime.replace(
    year=new_end_date.year,
    month=new_end_date.month,
    day=new_end_date.day,
    hour=16,
    minute=0
  )
  assert res == expected_end_datetime

def test_changing_startDate_startTime_endDate():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=1)).date()
  new_start_time_str = "16:00"
  new_end_date = (current_end_datetime + timedelta(days=2)).date()
  
  with pytest.raises(Exception) as excinfo:
    get_new_end_datetime(
      current_length, 
      current_start_datetime, 
      current_end_datetime, 
      new_start_time_str=new_start_time_str, 
      new_start_date=new_start_date,
      new_end_date=new_end_date
    )

  error_msg = "Invalid parameter combination: new_end_date provided without new_end_time_str while new_start_time_str is set."
  assert error_msg == str(excinfo.value)

def test_changing_startDate_startTime_endTime():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=1)).date()
  new_start_time_str = "15:00"
  new_end_time_str = "16:00"

  res = get_new_end_datetime(
    current_length, 
    current_start_datetime, 
    current_end_datetime, 
    new_start_date=new_start_date, 
    new_start_time_str=new_start_time_str,
    new_end_time_str=new_end_time_str
  )
  expected_end_datetime = current_end_datetime.replace(
    year=new_start_date.year,
    month=new_start_date.month,
    day=new_start_date.day,
    hour=16,
    minute=0
  )
  assert res == expected_end_datetime

def test_changing_startDate_endDate_endTime():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=1)).date()
  new_end_date = (current_start_datetime + timedelta(days=2)).date()
  new_end_time_str = "16:00"

  res = get_new_end_datetime(
    current_length, 
    current_start_datetime, 
    current_end_datetime, 
    new_start_date=new_start_date, 
    new_end_date=new_end_date,
    new_end_time_str=new_end_time_str
  )
  expected_end_datetime = current_end_datetime.replace(
    year=new_end_date.year,
    month=new_end_date.month,
    day=new_end_date.day,
    hour=16,
    minute=0
  )
  assert res == expected_end_datetime

def test_changing_startTime_endDate_endTime():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_time_str = "15:00"
  new_end_date = (current_start_datetime + timedelta(days=2)).date()
  new_end_time_str = "16:00"

  res = get_new_end_datetime(
    current_length, 
    current_start_datetime, 
    current_end_datetime, 
    new_start_time_str=new_start_time_str, 
    new_end_date=new_end_date,
    new_end_time_str=new_end_time_str
  )
  expected_end_datetime = current_end_datetime.replace(
    year=new_end_date.year,
    month=new_end_date.month,
    day=new_end_date.day,
    hour=16,
    minute=0
  )
  assert res == expected_end_datetime

def test_changing_startDate_startTime_endDate_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=1)).date()
  new_start_time_str = "15:00"
  new_end_date = (current_start_datetime + timedelta(days=2)).date()
  new_length_minutes = 999
  
  with pytest.raises(Exception) as excinfo:
    get_new_end_datetime(
      current_length, 
      current_start_datetime, 
      current_end_datetime, 
      new_start_time_str=new_start_time_str, 
      new_start_date=new_start_date,
      new_end_date=new_end_date,
      new_length_minutes=new_length_minutes
    )

  error_msg = "Invalid parameter combination: new_end_date and new_length_minutes provided without new_end_time_str while new_start_time_str is set."
  assert error_msg == str(excinfo.value)

def test_changing_startDate_startTime_endTime_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=1)).date()
  new_start_time_str = "15:00"
  new_end_time_str = "16:00"
  new_length_minutes = 999

  res = get_new_end_datetime(
    current_length, 
    current_start_datetime, 
    current_end_datetime, 
    new_start_time_str=new_start_time_str, 
    new_start_date=new_start_date,
    new_end_time_str=new_end_time_str,
    new_length_minutes=new_length_minutes
  )
  expected_end_datetime = current_end_datetime.replace(
    year=new_start_date.year,
    month=new_start_date.month,
    day=new_start_date.day,
    hour=16,
    minute=0
  )
  assert res == expected_end_datetime

def test_changing_startDate_endDate_endTime_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=1)).date()
  new_end_date = (current_start_datetime + timedelta(days=2)).date()
  new_end_time_str = "16:00"
  new_length_minutes = 999

  res = get_new_end_datetime(
    current_length, 
    current_start_datetime, 
    current_end_datetime, 
    new_end_date=new_end_date, 
    new_start_date=new_start_date,
    new_end_time_str=new_end_time_str,
    new_length_minutes=new_length_minutes
  )
  expected_end_datetime = current_end_datetime.replace(
    year=new_end_date.year,
    month=new_end_date.month,
    day=new_end_date.day,
    hour=16,
    minute=0
  )
  assert res == expected_end_datetime

def test_changing_startTime_endDate_endTime_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_time_str = "15:00"
  new_end_date = (current_start_datetime + timedelta(days=1)).date()
  new_end_time_str = "16:00"
  new_length_minutes = 999

  res = get_new_end_datetime(
    current_length, 
    current_start_datetime, 
    current_end_datetime, 
    new_end_date=new_end_date, 
    new_start_time_str=new_start_time_str,
    new_end_time_str=new_end_time_str,
    new_length_minutes=new_length_minutes
  )
  expected_end_datetime = current_end_datetime.replace(
    year=new_end_date.year,
    month=new_end_date.month,
    day=new_end_date.day,
    hour=16,
    minute=0
  )
  assert res == expected_end_datetime

def test_changing_startDate_startTime_endDate_endTime():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=1)).date()
  new_start_time_str = "15:00"
  new_end_date = (current_start_datetime + timedelta(days=2)).date()
  new_end_time_str = "16:00"

  res = get_new_end_datetime(
    current_length, 
    current_start_datetime, 
    current_end_datetime, 
    new_end_date=new_end_date, 
    new_start_time_str=new_start_time_str,
    new_end_time_str=new_end_time_str,
    new_start_date=new_start_date
  )
  expected_end_datetime = current_end_datetime.replace(
    year=new_end_date.year,
    month=new_end_date.month,
    day=new_end_date.day,
    hour=16,
    minute=0
  )
  assert res == expected_end_datetime

def test_changing_startDate_startTime_endDate_endTime_length():
  current_start_datetime =datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
  current_end_datetime = datetime.now(timezone.utc).replace(hour=0, minute=30, second=0, microsecond=0)
  current_length = 30  # in minutes
  new_start_date = (current_start_datetime + timedelta(days=1)).date()
  new_start_time_str = "15:00"
  new_end_date = (current_start_datetime + timedelta(days=2)).date()
  new_end_time_str = "16:00"
  new_length_minutes = 999

  res = get_new_end_datetime(
    current_length, 
    current_start_datetime, 
    current_end_datetime, 
    new_end_date=new_end_date, 
    new_start_time_str=new_start_time_str,
    new_end_time_str=new_end_time_str,
    new_start_date=new_start_date,
    new_length_minutes=new_length_minutes
  )
  expected_end_datetime = current_end_datetime.replace(
    year=new_end_date.year,
    month=new_end_date.month,
    day=new_end_date.day,
    hour=16,
    minute=0
  )
  assert res == expected_end_datetime