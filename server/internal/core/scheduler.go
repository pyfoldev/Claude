package core

import (
	"context"
	"log"
	"time"
)

// RunDue запускает агентов по расписанию (телефон для этого не нужен).
func (a *App) RunDue(now time.Time) {
	list, err := a.St.EnabledSchedules()
	if err != nil {
		log.Printf("schedules: %v", err)
		return
	}
	for _, s := range list {
		sched, err := cronParser.Parse(s.Cron)
		if err != nil {
			continue
		}
		loc, err := time.LoadLocation(s.Zone)
		if err != nil {
			loc = time.UTC
		}
		base := s.CreatedAt
		if s.LastRunAt > 0 {
			base = s.LastRunAt
		}
		if sched.Next(time.UnixMilli(base).In(loc)).After(now) {
			continue
		}
		ag, _ := a.St.AgentByID(s.AgentID)
		if ag == nil {
			continue
		}
		_ = a.St.MarkScheduleRun(s.ID, now.UnixMilli())
		a.addUserTranscript(ag.ID, "Плановое задание: "+s.Prompt)
		a.Post(ag, "system", "system", map[string]any{"text": "Плановое задание: " + s.Prompt})
		a.Enqueue(ag.ID)
	}
}

// StartScheduler проверяет расписания раз в 30 секунд до отмены ctx.
func (a *App) StartScheduler(ctx context.Context) {
	go func() {
		t := time.NewTicker(30 * time.Second)
		defer t.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case now := <-t.C:
				a.RunDue(now)
			}
		}
	}()
}
