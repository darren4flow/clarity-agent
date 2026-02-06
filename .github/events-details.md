## How Event Mapping Works Within Clarity

Events come in two forms:

- **Saved events**: explicitly stored calendar items.
- **Repeating event configs** (habits): templates that generate unsaved events on the calendar.

---

## Saved Events

- `startDate`: ISO string
- `endDate`: ISO string

---

## Repeating Event Config (Habit) Properties

- `creationDate`: first day events can start generating
- `frequency`: generation cadence anchored to `creationDate`  
  Examples: `'1D'`, `'2W'`, `'1M'`, `'1M3'` (every month on 3rd occurrence of a day), `'1Y'`
- `days`: used with `frequency`  
  - Weekly: `['Mon', 'Wed', 'Fri']`  
  - Monthly (by day of month): `['15']`  
  - Monthly (by weekday occurrence): `['1M2']`, `['Mon']` (second Monday)  
  - Yearly: `['Jan 15']`
- `exceptionDates`: days to skip because a saved event exists on that date
- `stopDate`: events cannot be generated on this day or after.
- `startTime`: time of day (hour, minute, timezone)
- `length`: duration in minutes (used to compute end time)


