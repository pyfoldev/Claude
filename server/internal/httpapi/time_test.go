package httpapi_test

import "time"

func timeAt(year int) time.Time { return time.Date(year, 1, 1, 12, 0, 0, 0, time.UTC) }
