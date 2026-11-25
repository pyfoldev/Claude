package httpapi

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/robfig/cron/v3"

	"staika/server/internal/core"
	"staika/server/internal/llm"
	"staika/server/internal/store"
)

type agentReq struct {
	Name     string      `json:"name"`
	Role     string      `json:"role"`
	Pal      string      `json:"pal"`
	Model    string      `json:"model"`
	ParentID string      `json:"parentId"`
	Chief    bool        `json:"chief"`
	Perms    *core.Perms `json:"perms"`
}

func clip(s string, n int) string {
	r := []rune(strings.TrimSpace(s))
	if len(r) > n {
		return string(r[:n])
	}
	return string(r)
}

func (s *Server) apiRoutes(m *http.ServeMux) {
	m.HandleFunc("GET /api/models", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		s.writeJSON(w, 200, llm.Catalog)
	}))

	m.HandleFunc("GET /api/agents", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		list, err := s.St.AgentsForUser(p.UserID)
		if err != nil {
			s.fail(w, err)
			return
		}
		out := make([]core.AgentDTO, 0, len(list))
		for i := range list {
			out = append(out, s.App.AgentDTO(&list[i]))
		}
		s.writeJSON(w, 200, out)
	}))

	m.HandleFunc("POST /api/agents", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		var b agentReq
		if !s.decode(w, r, &b) {
			return
		}
		u, err := s.user(p)
		if err != nil {
			s.fail(w, err)
			return
		}
		if strings.TrimSpace(b.Name) == "" {
			s.fail(w, core.BadRequest("bad_name", "Укажите имя агента"))
			return
		}
		if b.Model == "" {
			b.Model = "Claude Haiku 4.5"
		}
		if llm.Find(b.Model) == nil {
			s.fail(w, core.BadRequest("bad_model", "Неизвестная модель"))
			return
		}
		limit := 10
		if u.IsOwner() {
			limit = 40
		}
		if n, _ := s.St.CountAgents(u.ID); n >= limit {
			s.fail(w, core.Forbidden("Достигнут лимит агентов"))
			return
		}
		parent := ""
		if b.ParentID != "" {
			pa, err := s.ownAgent(p, b.ParentID)
			if err != nil {
				s.fail(w, err)
				return
			}
			parent = pa.ID
		}
		if b.Chief {
			all, _ := s.St.AgentsForUser(u.ID)
			for _, a := range all {
				if a.Chief {
					s.fail(w, core.BadRequest("chief_exists", "Главный агент уже есть"))
					return
				}
			}
		}
		perms := core.Perms{AlwaysAllow: []string{}}
		if b.Perms != nil {
			perms.Browser, perms.Mail = b.Perms.Browser, b.Perms.Mail
			perms.Server = b.Perms.Server && u.CanUseShell()
		}
		pb, _ := json.Marshal(perms)
		if b.Pal == "" {
			b.Pal = "Cloud"
		}
		a := &store.Agent{ID: store.NewID(), UserID: u.ID, ParentID: parent, Name: clip(b.Name, 60), RoleDesc: clip(b.Role, 1000), Pal: clip(b.Pal, 20),
			Model: b.Model, Chief: b.Chief, Perms: string(pb), Status: "Idle", LastText: "Готов к работе. Поставьте первую задачу.",
			LastAt: store.Now(), TokenLimit: 2_000_000, CreatedAt: store.Now()}
		if err := s.St.CreateAgent(a); err != nil {
			s.fail(w, err)
			return
		}
		s.St.Audit(u.ID, a.ID, "agent_create", a.Name)
		s.writeJSON(w, 201, s.App.AgentDTO(a))
	}))

	m.HandleFunc("PUT /api/agents/{id}", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		a, err := s.ownAgent(p, r.PathValue("id"))
		if err != nil {
			s.fail(w, err)
			return
		}
		var b agentReq
		if !s.decode(w, r, &b) {
			return
		}
		u, _ := s.user(p)
		if b.Model == "" {
			b.Model = a.Model
		}
		if llm.Find(b.Model) == nil {
			s.fail(w, core.BadRequest("bad_model", "Неизвестная модель"))
			return
		}
		parent := ""
		if b.ParentID != "" {
			pa, err := s.ownAgent(p, b.ParentID)
			if err != nil {
				s.fail(w, err)
				return
			}
			if pa.ID == a.ID {
				s.fail(w, core.BadRequest("bad_parent", "Агент не может подчиняться самому себе"))
				return
			}
			parent = pa.ID
		}
		old := s.App.PermsOf(a)
		np := old
		if b.Perms != nil {
			np.Browser, np.Mail = b.Perms.Browser, b.Perms.Mail
			np.Server = b.Perms.Server && u != nil && u.CanUseShell()
		}
		pb, _ := json.Marshal(np)
		if n := clip(b.Name, 60); n != "" {
			a.Name = n
		}
		a.RoleDesc, a.Pal, a.Model, a.ParentID, a.Perms = clip(b.Role, 1000), orDefault(clip(b.Pal, 20), a.Pal), b.Model, parent, string(pb)
		if err := s.St.UpdateAgent(a); err != nil {
			s.fail(w, err)
			return
		}
		s.writeJSON(w, 200, s.App.AgentDTO(a))
	}))

	m.HandleFunc("DELETE /api/agents/{id}", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		a, err := s.ownAgent(p, r.PathValue("id"))
		if err != nil {
			s.fail(w, err)
			return
		}
		kids, _ := s.St.Children(a.ID)
		for i := range kids {
			kids[i].ParentID = ""
			_ = s.St.UpdateAgent(&kids[i])
		}
		_ = s.St.DeleteAgent(a.ID)
		s.St.Audit(p.UserID, a.ID, "agent_delete", a.Name)
		s.writeJSON(w, 200, map[string]bool{"ok": true})
	}))

	m.HandleFunc("GET /api/agents/{id}/messages", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		a, err := s.ownAgent(p, r.PathValue("id"))
		if err != nil {
			s.fail(w, err)
			return
		}
		before, limit := int64(1<<62), 50
		if v, err := strconv.ParseInt(r.URL.Query().Get("before"), 10, 64); err == nil {
			before = v
		}
		if v, err := strconv.Atoi(r.URL.Query().Get("limit")); err == nil && v > 0 && v <= 200 {
			limit = v
		}
		rows, err := s.St.MessagePage(a.ID, before, limit)
		if err != nil {
			s.fail(w, err)
			return
		}
		out := make([]core.MessageDTO, 0, len(rows))
		for i := range rows {
			out = append(out, s.App.MessageDTO(&rows[i]))
		}
		s.writeJSON(w, 200, out)
	}))

	m.HandleFunc("POST /api/agents/{id}/messages", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		a, err := s.ownAgent(p, r.PathValue("id"))
		if err != nil {
			s.fail(w, err)
			return
		}
		var b struct {
			Text string `json:"text"`
		}
		if !s.decode(w, r, &b) {
			return
		}
		text := strings.TrimSpace(b.Text)
		if text == "" {
			s.fail(w, core.BadRequest("empty", "Пустое сообщение"))
			return
		}
		if len([]rune(text)) > 8000 {
			s.fail(w, core.BadRequest("too_long", "Сообщение слишком длинное"))
			return
		}
		if err := s.Limiter.Check("send:"+p.UserID, 40, time.Minute); err != nil {
			s.fail(w, err)
			return
		}
		msg := s.App.Post(a, "user", "text", map[string]any{"text": text})
		s.App.AddUserMessageToContext(a.ID, text)
		s.App.Enqueue(a.ID)
		s.writeJSON(w, 201, s.App.MessageDTO(msg))
	}))

	m.HandleFunc("PUT /api/profile", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		var b struct {
			Name string `json:"name"`
		}
		if !s.decode(w, r, &b) {
			return
		}
		if strings.TrimSpace(b.Name) == "" {
			s.fail(w, core.BadRequest("bad_name", "Укажите имя"))
			return
		}
		_ = s.St.SetName(p.UserID, clip(b.Name, 80))
		u, err := s.user(p)
		if err != nil {
			s.fail(w, err)
			return
		}
		s.writeJSON(w, 200, core.DTO(u))
	}))

	// ---------- подтверждения и задачи ----------
	m.HandleFunc("GET /api/approvals", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		list, err := s.St.PendingForUser(p.UserID)
		if err != nil {
			s.fail(w, err)
			return
		}
		if list == nil {
			list = []store.Approval{}
		}
		s.writeJSON(w, 200, list)
	}))
	m.HandleFunc("POST /api/approvals/{id}/decision", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		var b struct {
			Allow  bool `json:"allow"`
			Always bool `json:"always"`
		}
		if !s.decode(w, r, &b) {
			return
		}
		ap, err := s.App.DecideApproval(p.UserID, r.PathValue("id"), b.Allow, b.Always)
		if err != nil {
			s.fail(w, err)
			return
		}
		s.writeJSON(w, 200, map[string]string{"id": ap.ID, "status": ap.Status})
	}))
	m.HandleFunc("GET /api/tasks", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		t, err := s.St.TasksForUser(p.UserID)
		if err != nil {
			s.fail(w, err)
			return
		}
		s.writeJSON(w, 200, t)
	}))

	// ---------- ключи провайдеров ----------
	m.HandleFunc("GET /api/keys", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		u, err := s.user(p)
		if err != nil {
			s.fail(w, err)
			return
		}
		own, _ := s.St.KeyProviders(u.ID)
		s.writeJSON(w, 200, map[string]any{"own": own, "serverKeysAllowed": u.CanUseServerKeys()})
	}))
	m.HandleFunc("PUT /api/keys/{provider}", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		prov := r.PathValue("provider")
		switch prov {
		case "anthropic", "openai", "google", "river", "deepgram":
		default:
			s.fail(w, core.BadRequest("bad_provider", "Неизвестный провайдер"))
			return
		}
		var b struct {
			Key string `json:"key"`
		}
		if !s.decode(w, r, &b) {
			return
		}
		k := strings.TrimSpace(b.Key)
		if k == "" || len(k) > 500 {
			s.fail(w, core.BadRequest("bad_key", "Некорректный ключ"))
			return
		}
		if err := s.St.PutKey(p.UserID, prov, s.Box.Seal(k)); err != nil {
			s.fail(w, err)
			return
		}
		s.St.Audit(p.UserID, "", "key_set", prov)
		s.writeJSON(w, 200, map[string]bool{"ok": true})
	}))
	m.HandleFunc("DELETE /api/keys/{provider}", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		_ = s.St.DeleteKey(p.UserID, r.PathValue("provider"))
		s.writeJSON(w, 200, map[string]bool{"ok": true})
	}))

	// ---------- расписания ----------
	m.HandleFunc("GET /api/schedules", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		l, err := s.St.SchedulesForUser(p.UserID)
		if err != nil {
			s.fail(w, err)
			return
		}
		s.writeJSON(w, 200, l)
	}))
	m.HandleFunc("POST /api/schedules", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		var b struct{ AgentID, Cron, Prompt, Zone string }
		var raw struct {
			AgentID string `json:"agentId"`
			Cron    string `json:"cron"`
			Prompt  string `json:"prompt"`
			Zone    string `json:"zone"`
		}
		if !s.decode(w, r, &raw) {
			return
		}
		b.AgentID, b.Cron, b.Prompt, b.Zone = raw.AgentID, raw.Cron, raw.Prompt, raw.Zone
		a, err := s.ownAgent(p, b.AgentID)
		if err != nil {
			s.fail(w, err)
			return
		}
		if _, err := cron.NewParser(cron.Second | cron.Minute | cron.Hour | cron.Dom | cron.Month | cron.Dow | cron.Descriptor).Parse(b.Cron); err != nil {
			s.fail(w, core.BadRequest("bad_cron", "Некорректное cron-выражение (6 полей: сек мин час день месяц день_недели)"))
			return
		}
		if b.Zone == "" {
			b.Zone = "UTC"
		}
		if _, err := time.LoadLocation(b.Zone); err != nil {
			s.fail(w, core.BadRequest("bad_zone", "Неизвестный часовой пояс"))
			return
		}
		if strings.TrimSpace(b.Prompt) == "" {
			s.fail(w, core.BadRequest("bad_prompt", "Укажите задание"))
			return
		}
		if l, _ := s.St.SchedulesForUser(p.UserID); len(l) >= 50 {
			s.fail(w, core.Forbidden("Слишком много расписаний"))
			return
		}
		sc, err := s.St.CreateSchedule(p.UserID, a.ID, b.Cron, b.Zone, clip(b.Prompt, 2000))
		if err != nil {
			s.fail(w, err)
			return
		}
		s.writeJSON(w, 201, sc)
	}))
	m.HandleFunc("DELETE /api/schedules/{id}", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		sc, _ := s.St.ScheduleByID(r.PathValue("id"))
		if sc == nil || sc.UserID != p.UserID {
			s.fail(w, core.NotFound("Не найдено"))
			return
		}
		_ = s.St.DeleteSchedule(sc.ID)
		s.writeJSON(w, 200, map[string]bool{"ok": true})
	}))
	m.HandleFunc("PUT /api/schedules/{id}/enabled", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		sc, _ := s.St.ScheduleByID(r.PathValue("id"))
		if sc == nil || sc.UserID != p.UserID {
			s.fail(w, core.NotFound("Не найдено"))
			return
		}
		_ = s.St.SetScheduleEnabled(sc.ID, r.URL.Query().Get("on") == "true")
		s.writeJSON(w, 200, map[string]bool{"ok": true})
	}))

	// ---------- статистика, журнал, устройства, админка ----------
	m.HandleFunc("GET /api/stats", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		since := time.Now().UTC().AddDate(0, 0, -6)
		since = time.Date(since.Year(), since.Month(), since.Day(), 0, 0, 0, 0, time.UTC)
		rows, err := s.St.UsageSummary(p.UserID, since.UnixMilli())
		if err != nil {
			s.fail(w, err)
			return
		}
		s.writeJSON(w, 200, map[string]any{"sinceMs": since.UnixMilli(), "byAgent": rows})
	}))
	m.HandleFunc("GET /api/audit", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		rows, err := s.St.RecentAudit(p.UserID, 100)
		if err != nil {
			s.fail(w, err)
			return
		}
		s.writeJSON(w, 200, rows)
	}))
	m.HandleFunc("POST /api/devices", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		var b struct {
			FcmToken string `json:"fcmToken"`
		}
		if !s.decode(w, r, &b) {
			return
		}
		if strings.TrimSpace(b.FcmToken) == "" {
			s.fail(w, core.BadRequest("bad_token", "Пустой токен"))
			return
		}
		_ = s.St.RegisterDevice(p.UserID, b.FcmToken)
		s.writeJSON(w, 200, map[string]bool{"ok": true})
	}))
	owner := func(h authed) http.HandlerFunc {
		return s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
			u, err := s.user(p)
			if err != nil || !u.IsOwner() {
				s.fail(w, core.Forbidden("Только для владельца"))
				return
			}
			h(w, r, p)
		})
	}
	m.HandleFunc("GET /api/admin/users", owner(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		us, err := s.St.ListUsers()
		if err != nil {
			s.fail(w, err)
			return
		}
		out := []core.UserDTO{}
		for i := range us {
			out = append(out, core.DTO(&us[i]))
		}
		s.writeJSON(w, 200, out)
	}))
	m.HandleFunc("PUT /api/admin/users/{id}/role", owner(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		var b struct {
			Role string `json:"role"`
		}
		if !s.decode(w, r, &b) {
			return
		}
		if b.Role != "member" && b.Role != "family" && b.Role != "owner" {
			s.fail(w, core.BadRequest("bad_role", "Допустимо: member, family, owner"))
			return
		}
		id := r.PathValue("id")
		if id == p.UserID && b.Role != "owner" {
			s.fail(w, core.BadRequest("self_demote", "Нельзя понизить себя"))
			return
		}
		if u, _ := s.St.UserByID(id); u == nil {
			s.fail(w, core.NotFound("Пользователь не найден"))
			return
		}
		_ = s.St.SetRole(id, b.Role)
		s.writeJSON(w, 200, map[string]bool{"ok": true})
	}))
}

func orDefault(v, def string) string {
	if v == "" {
		return def
	}
	return v
}
