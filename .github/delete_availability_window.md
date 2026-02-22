The delete_availability_window function will have many similarities to the delete_event function inside of delete_event_tool.py.

Study the implementation of delete_event to help you understand the algorithm for the delete_availability_window below. Then implement this function inside of delete_availability_window_tool.py

# The Algorithm
  ```python
  windows = getAvailabilityWindowsOnDate(start_date) #this will get the saved windows and the unsaved windows
  if len(windows) > 1 and not start_time:
    return "need a start time"
  elif len(windows) > 1 and start_time:
    window = searchWindowsForMatch(windows, start_time)
    if not window:
      return "no {type} availability window found matching that date and time"
  elif len(windows) == 1:
    window = windows[0]
  else:
    return "no availability windows found on that date"

  if window.habitId:
    if this_window_only or this_and_future_windows:
      if this_window_only:
        return deleteThisWindowOnly(window.id)
      else:
        return deleteThisAndFutureWindows(window.id)
    else:
      return "this is a recurring availability window. Should I delete this window only or this and future windows?"
  else:
    return deleteWindow(window.id)
  ```
   
##### Notes on getAvailabilityWindowsOnDate(start_date)
This will get the saved and unsaved (repeating) windows for a given date. It will get the unsaved ones by using the isRepeatingOnDay function in utils. When creating the list, it will create objects that have an id, habitId, startDate, endDate, startTime, endTime, and type
