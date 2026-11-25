package store

import (
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"strings"
)

func NewID() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	h := hex.EncodeToString(b)
	return h[0:8] + "-" + h[8:12] + "-" + h[12:16] + "-" + h[16:20] + "-" + h[20:]
}

func ns(s sql.NullString) string { return s.String }

// ---------- users ----------

const userCols = "id,email,name,password_hash,google_sub,role,email_verified,created_at"

func scanUser(r interface{ Scan(...any) error }) (*User, error) {
	var u User
	var ph, gs sql.NullString
	var ev int
	if err := r.Scan(&u.ID, &u.Email, &u.Name, &ph, &gs, &u.Role, &ev, &u.CreatedAt); err != nil {
		return nil, nf(err)
	}
	u.PasswordHash, u.GoogleSub, u.EmailVerified = ns(ph), ns(gs), ev == 1
	return &u, nil
}

func (s *Store) UserByID(id string) (*User, error) {
	return scanUser(s.DB.QueryRow("SELECT "+userCols+" FROM users WHERE id=?", id))
}
func (s *Store) UserByEmail(e string) (*User, error) {
	return scanUser(s.DB.QueryRow("SELECT "+userCols+" FROM users WHERE email=?", strings.ToLower(e)))
}
func (s *Store) UserByGoogle(sub string) (*User, error) {
	return scanUser(s.DB.QueryRow("SELECT "+userCols+" FROM users WHERE google_sub=?", sub))
}
func (s *Store) CountUsers() (n int, err error) {
	err = s.DB.QueryRow("SELECT COUNT(*) FROM users").Scan(&n)
	return
}
func (s *Store) ListUsers() ([]User, error) {
	rows, err := s.DB.Query("SELECT " + userCols + " FROM users ORDER BY created_at")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []User
	for rows.Next() {
		u, err := scanUser(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, *u)
	}
	return out, rows.Err()
}
func (s *Store) CreateUser(email, name, hash, googleSub, role string, verified bool) (*User, error) {
	id := NewID()
	var h, g any
	if hash != "" {
		h = hash
	}
	if googleSub != "" {
		g = googleSub
	}
	_, err := s.DB.Exec("INSERT INTO users(id,email,name,password_hash,google_sub,role,email_verified,created_at) VALUES(?,?,?,?,?,?,?,?)",
		id, strings.ToLower(email), name, h, g, role, b2i(verified), Now())
	if err != nil {
		return nil, err
	}
	return s.UserByID(id)
}
func (s *Store) SetPassword(id, hash string) error {
	_, err := s.DB.Exec("UPDATE users SET password_hash=? WHERE id=?", hash, id)
	return err
}
func (s *Store) SetVerified(id string) error {
	_, err := s.DB.Exec("UPDATE users SET email_verified=1 WHERE id=?", id)
	return err
}
func (s *Store) SetGoogle(id, sub string) error {
	_, err := s.DB.Exec("UPDATE users SET google_sub=?, email_verified=1 WHERE id=?", sub, id)
	return err
}
func (s *Store) SetRole(id, role string) error {
	_, err := s.DB.Exec("UPDATE users SET role=? WHERE id=?", role, id)
	return err
}
func (s *Store) SetName(id, name string) error {
	_, err := s.DB.Exec("UPDATE users SET name=? WHERE id=?", name, id)
	return err
}

// ---------- auth tokens & codes ----------

func (s *Store) AddRefresh(userID, hash, device string, expires int64) error {
	_, err := s.DB.Exec("INSERT INTO refresh_tokens(id,user_id,token_hash,device,expires_at,revoked,created_at) VALUES(?,?,?,?,?,0,?)",
		NewID(), userID, hash, device, expires, Now())
	return err
}

type RefreshRow struct {
	ID, UserID string
	Expires    int64
	Revoked    bool
}

func (s *Store) RefreshByHash(hash string) (*RefreshRow, error) {
	var r RefreshRow
	var rv int
	err := s.DB.QueryRow("SELECT id,user_id,expires_at,revoked FROM refresh_tokens WHERE token_hash=?", hash).Scan(&r.ID, &r.UserID, &r.Expires, &rv)
	if err != nil {
		return nil, nf(err)
	}
	r.Revoked = rv == 1
	return &r, nil
}
func (s *Store) RevokeRefresh(id string) error {
	_, err := s.DB.Exec("UPDATE refresh_tokens SET revoked=1 WHERE id=?", id)
	return err
}
func (s *Store) RevokeRefreshByHash(h string) error {
	_, err := s.DB.Exec("UPDATE refresh_tokens SET revoked=1 WHERE token_hash=?", h)
	return err
}
func (s *Store) RevokeAllRefresh(userID string) error {
	_, err := s.DB.Exec("UPDATE refresh_tokens SET revoked=1 WHERE user_id=?", userID)
	return err
}

func (s *Store) AddCode(email, purpose, hash string, expires int64) error {
	if _, err := s.DB.Exec("UPDATE auth_codes SET used=1 WHERE email=? AND purpose=?", email, purpose); err != nil {
		return err
	}
	_, err := s.DB.Exec("INSERT INTO auth_codes(id,email,purpose,code_hash,expires_at,created_at) VALUES(?,?,?,?,?,?)",
		NewID(), email, purpose, hash, expires, Now())
	return err
}

type CodeRow struct {
	ID, Hash string
	Expires  int64
	Attempts int
}

func (s *Store) LatestCode(email, purpose string) (*CodeRow, error) {
	var c CodeRow
	err := s.DB.QueryRow("SELECT id,code_hash,expires_at,attempts FROM auth_codes WHERE email=? AND purpose=? AND used=0 ORDER BY created_at DESC LIMIT 1",
		email, purpose).Scan(&c.ID, &c.Hash, &c.Expires, &c.Attempts)
	if err != nil {
		return nil, nf(err)
	}
	return &c, nil
}
func (s *Store) CodeAttempt(id string) error {
	_, err := s.DB.Exec("UPDATE auth_codes SET attempts=attempts+1 WHERE id=?", id)
	return err
}
func (s *Store) CodeUsed(id string) error {
	_, err := s.DB.Exec("UPDATE auth_codes SET used=1 WHERE id=?", id)
	return err
}

// ---------- agents ----------

const agentCols = "id,user_id,parent_id,name,role_desc,pal,model,is_chief,perms,status,last_text,last_at,daily_token_limit,created_at"

func scanAgent(r interface{ Scan(...any) error }) (*Agent, error) {
	var a Agent
	var p sql.NullString
	var ch int
	if err := r.Scan(&a.ID, &a.UserID, &p, &a.Name, &a.RoleDesc, &a.Pal, &a.Model, &ch, &a.Perms, &a.Status, &a.LastText, &a.LastAt, &a.TokenLimit, &a.CreatedAt); err != nil {
		return nil, nf(err)
	}
	a.ParentID, a.Chief = ns(p), ch == 1
	return &a, nil
}

func (s *Store) AgentByID(id string) (*Agent, error) {
	return scanAgent(s.DB.QueryRow("SELECT "+agentCols+" FROM agents WHERE id=?", id))
}
func (s *Store) agentsWhere(where string, args ...any) ([]Agent, error) {
	rows, err := s.DB.Query("SELECT "+agentCols+" FROM agents WHERE "+where+" ORDER BY created_at", args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Agent
	for rows.Next() {
		a, err := scanAgent(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, *a)
	}
	return out, rows.Err()
}
func (s *Store) AgentsForUser(uid string) ([]Agent, error) { return s.agentsWhere("user_id=?", uid) }
func (s *Store) Children(id string) ([]Agent, error)       { return s.agentsWhere("parent_id=?", id) }
func (s *Store) CountAgents(uid string) (n int, err error) {
	err = s.DB.QueryRow("SELECT COUNT(*) FROM agents WHERE user_id=?", uid).Scan(&n)
	return
}
func (s *Store) CreateAgent(a *Agent) error {
	var p any
	if a.ParentID != "" {
		p = a.ParentID
	}
	_, err := s.DB.Exec("INSERT INTO agents("+agentCols+") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
		a.ID, a.UserID, p, a.Name, a.RoleDesc, a.Pal, a.Model, b2i(a.Chief), a.Perms, a.Status, a.LastText, a.LastAt, a.TokenLimit, a.CreatedAt)
	return err
}
func (s *Store) UpdateAgent(a *Agent) error {
	var p any
	if a.ParentID != "" {
		p = a.ParentID
	}
	_, err := s.DB.Exec("UPDATE agents SET name=?, role_desc=?, pal=?, model=?, parent_id=?, perms=? WHERE id=?",
		a.Name, a.RoleDesc, a.Pal, a.Model, p, a.Perms, a.ID)
	return err
}
func (s *Store) SetAgentStatus(id, st string) error {
	_, err := s.DB.Exec("UPDATE agents SET status=? WHERE id=?", st, id)
	return err
}
func (s *Store) SetAgentLast(id, text string, at int64) error {
	r := []rune(text)
	if len(r) > 200 {
		text = string(r[:200])
	}
	_, err := s.DB.Exec("UPDATE agents SET last_text=?, last_at=? WHERE id=?", text, at, id)
	return err
}
func (s *Store) DeleteAgent(id string) error {
	_, err := s.DB.Exec("DELETE FROM agents WHERE id=?", id)
	return err
}
func (s *Store) ResetWorking() error {
	_, err := s.DB.Exec("UPDATE agents SET status='Idle' WHERE status='Working'")
	return err
}

// ---------- messages & transcript ----------

func (s *Store) InsertMessage(m *Message) error {
	_, err := s.DB.Exec("INSERT INTO messages(id,agent_id,user_id,sender,type,content,created_at) VALUES(?,?,?,?,?,?,?)",
		m.ID, m.AgentID, m.UserID, m.Sender, m.Type, m.Content, m.CreatedAt)
	return err
}
func (s *Store) MessageByID(id string) (*Message, error) {
	var m Message
	err := s.DB.QueryRow("SELECT id,agent_id,user_id,sender,type,content,created_at FROM messages WHERE id=?", id).
		Scan(&m.ID, &m.AgentID, &m.UserID, &m.Sender, &m.Type, &m.Content, &m.CreatedAt)
	if err != nil {
		return nil, nf(err)
	}
	return &m, nil
}
func (s *Store) UpdateMessage(id, content string) error {
	_, err := s.DB.Exec("UPDATE messages SET content=? WHERE id=?", content, id)
	return err
}
func (s *Store) MessagePage(agentID string, before int64, limit int) ([]Message, error) {
	rows, err := s.DB.Query("SELECT id,agent_id,user_id,sender,type,content,created_at FROM messages WHERE agent_id=? AND created_at<? ORDER BY created_at DESC, id DESC LIMIT ?",
		agentID, before, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Message
	for rows.Next() {
		var m Message
		if err := rows.Scan(&m.ID, &m.AgentID, &m.UserID, &m.Sender, &m.Type, &m.Content, &m.CreatedAt); err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	for i, j := 0, len(out)-1; i < j; i, j = i+1, j-1 {
		out[i], out[j] = out[j], out[i]
	}
	return out, rows.Err()
}

func (s *Store) AddTranscript(agentID, role, content string) error {
	_, err := s.DB.Exec("INSERT INTO transcript(agent_id,role,content,created_at) VALUES(?,?,?,?)", agentID, role, content, Now())
	return err
}
func (s *Store) LastTranscript(agentID string, limit int) ([]TranscriptRow, error) {
	rows, err := s.DB.Query("SELECT id,agent_id,role,content FROM transcript WHERE agent_id=? ORDER BY id DESC LIMIT ?", agentID, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []TranscriptRow
	for rows.Next() {
		var r TranscriptRow
		if err := rows.Scan(&r.ID, &r.AgentID, &r.Role, &r.Content); err != nil {
			return nil, err
		}
		out = append(out, r)
	}
	for i, j := 0, len(out)-1; i < j; i, j = i+1, j-1 {
		out[i], out[j] = out[j], out[i]
	}
	return out, rows.Err()
}

// ---------- approvals ----------

const apprCols = "id,user_id,agent_id,message_id,tool_call_id,tool_name,args,summary,risk,status,created_at"

func scanAppr(r interface{ Scan(...any) error }) (*Approval, error) {
	var a Approval
	var m sql.NullString
	if err := r.Scan(&a.ID, &a.UserID, &a.AgentID, &m, &a.ToolCallID, &a.ToolName, &a.Args, &a.Summary, &a.Risk, &a.Status, &a.CreatedAt); err != nil {
		return nil, nf(err)
	}
	a.MessageID = ns(m)
	return &a, nil
}
func (s *Store) ApprovalByID(id string) (*Approval, error) {
	return scanAppr(s.DB.QueryRow("SELECT "+apprCols+" FROM approvals WHERE id=?", id))
}
func (s *Store) approvalsWhere(where string, args ...any) ([]Approval, error) {
	rows, err := s.DB.Query("SELECT "+apprCols+" FROM approvals WHERE "+where+" ORDER BY created_at", args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Approval
	for rows.Next() {
		a, err := scanAppr(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, *a)
	}
	return out, rows.Err()
}
func (s *Store) PendingForUser(uid string) ([]Approval, error) {
	return s.approvalsWhere("user_id=? AND status='pending'", uid)
}
func (s *Store) PendingForAgent(id string) ([]Approval, error) {
	return s.approvalsWhere("agent_id=? AND status='pending'", id)
}
func (s *Store) InsertApproval(a *Approval) error {
	var m any
	if a.MessageID != "" {
		m = a.MessageID
	}
	_, err := s.DB.Exec("INSERT INTO approvals("+apprCols+") VALUES(?,?,?,?,?,?,?,?,?,?,?)",
		a.ID, a.UserID, a.AgentID, m, a.ToolCallID, a.ToolName, a.Args, a.Summary, a.Risk, a.Status, a.CreatedAt)
	return err
}

// DecideApproval возвращает false, если решение уже было принято (защита от гонки).
func (s *Store) DecideApproval(id, status string) (bool, error) {
	r, err := s.DB.Exec("UPDATE approvals SET status=?, decided_at=? WHERE id=? AND status='pending'", status, Now(), id)
	if err != nil {
		return false, err
	}
	n, _ := r.RowsAffected()
	return n == 1, nil
}

// ---------- tasks ----------

const taskCols = "id,user_id,from_agent,to_agent,title,status,progress,result,created_at,updated_at"

func scanTask(r interface{ Scan(...any) error }) (*Task, error) {
	var t Task
	var f, res sql.NullString
	if err := r.Scan(&t.ID, &t.UserID, &f, &t.ToAgent, &t.Title, &t.Status, &t.Progress, &res, &t.CreatedAt, &t.UpdatedAt); err != nil {
		return nil, nf(err)
	}
	t.FromAgent, t.Result = ns(f), ns(res)
	return &t, nil
}
func (s *Store) TaskByID(id string) (*Task, error) {
	return scanTask(s.DB.QueryRow("SELECT "+taskCols+" FROM tasks WHERE id=?", id))
}
func (s *Store) TasksForUser(uid string) ([]Task, error) {
	rows, err := s.DB.Query("SELECT "+taskCols+" FROM tasks WHERE user_id=? ORDER BY updated_at DESC LIMIT 200", uid)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Task{}
	for rows.Next() {
		t, err := scanTask(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, *t)
	}
	return out, rows.Err()
}
func (s *Store) CreateTask(uid, from, to, title string) (*Task, error) {
	id := NewID()
	var f any
	if from != "" {
		f = from
	}
	t := Now()
	if _, err := s.DB.Exec("INSERT INTO tasks(id,user_id,from_agent,to_agent,title,status,progress,created_at,updated_at) VALUES(?,?,?,?,?,'В работе',0,?,?)",
		id, uid, f, to, title, t, t); err != nil {
		return nil, err
	}
	return s.TaskByID(id)
}
func (s *Store) FinishTask(id, status, result string) error {
	p := 0.5
	if status == "Готово" {
		p = 1
	}
	_, err := s.DB.Exec("UPDATE tasks SET status=?, progress=?, result=?, updated_at=? WHERE id=?", status, p, result, Now(), id)
	return err
}

// ---------- memories, keys, schedules, usage, audit, devices ----------

func (s *Store) AddMemory(agentID, text string) error {
	_, err := s.DB.Exec("INSERT INTO memories(id,agent_id,text,created_at) VALUES(?,?,?,?)", NewID(), agentID, text, Now())
	return err
}
func (s *Store) texts(q string, args ...any) ([]string, error) {
	rows, err := s.DB.Query(q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []string
	for rows.Next() {
		var t string
		if err := rows.Scan(&t); err != nil {
			return nil, err
		}
		out = append(out, t)
	}
	for i, j := 0, len(out)-1; i < j; i, j = i+1, j-1 {
		out[i], out[j] = out[j], out[i]
	}
	return out, rows.Err()
}
func (s *Store) RecentMemories(agentID string, n int) ([]string, error) {
	return s.texts("SELECT text FROM memories WHERE agent_id=? ORDER BY created_at DESC, id DESC LIMIT ?", agentID, n)
}
func (s *Store) SearchMemories(agentID, q string) ([]string, error) {
	q = strings.NewReplacer("%", "", "_", "").Replace(strings.ToLower(q))
	return s.texts("SELECT text FROM memories WHERE agent_id=? AND LOWER(text) LIKE ? ORDER BY created_at DESC LIMIT 20", agentID, "%"+q+"%")
}

func (s *Store) GetKey(uid, provider string) (string, error) {
	var c string
	err := s.DB.QueryRow("SELECT ciphertext FROM provider_keys WHERE user_id=? AND provider=?", uid, provider).Scan(&c)
	return c, nf(err)
}
func (s *Store) KeyProviders(uid string) ([]string, error) {
	rows, err := s.DB.Query("SELECT provider FROM provider_keys WHERE user_id=?", uid)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []string{}
	for rows.Next() {
		var p string
		if err := rows.Scan(&p); err != nil {
			return nil, err
		}
		out = append(out, p)
	}
	return out, rows.Err()
}
func (s *Store) PutKey(uid, provider, cipher string) error {
	if _, err := s.DB.Exec("DELETE FROM provider_keys WHERE user_id=? AND provider=?", uid, provider); err != nil {
		return err
	}
	_, err := s.DB.Exec("INSERT INTO provider_keys(id,user_id,provider,ciphertext,created_at) VALUES(?,?,?,?,?)", NewID(), uid, provider, cipher, Now())
	return err
}
func (s *Store) DeleteKey(uid, provider string) error {
	_, err := s.DB.Exec("DELETE FROM provider_keys WHERE user_id=? AND provider=?", uid, provider)
	return err
}

const schedCols = "id,user_id,agent_id,cron,zone,prompt,enabled,last_run_at,created_at"

func scanSched(r interface{ Scan(...any) error }) (*Schedule, error) {
	var x Schedule
	var en int
	var lr sql.NullInt64
	if err := r.Scan(&x.ID, &x.UserID, &x.AgentID, &x.Cron, &x.Zone, &x.Prompt, &en, &lr, &x.CreatedAt); err != nil {
		return nil, nf(err)
	}
	x.Enabled, x.LastRunAt = en == 1, lr.Int64
	return &x, nil
}
func (s *Store) schedWhere(where string, args ...any) ([]Schedule, error) {
	rows, err := s.DB.Query("SELECT "+schedCols+" FROM schedules WHERE "+where+" ORDER BY created_at", args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []Schedule{}
	for rows.Next() {
		x, err := scanSched(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, *x)
	}
	return out, rows.Err()
}
func (s *Store) SchedulesForUser(uid string) ([]Schedule, error) {
	return s.schedWhere("user_id=?", uid)
}
func (s *Store) EnabledSchedules() ([]Schedule, error) { return s.schedWhere("enabled=1") }
func (s *Store) ScheduleByID(id string) (*Schedule, error) {
	return scanSched(s.DB.QueryRow("SELECT "+schedCols+" FROM schedules WHERE id=?", id))
}
func (s *Store) CreateSchedule(uid, agentID, cron, zone, prompt string) (*Schedule, error) {
	id := NewID()
	if _, err := s.DB.Exec("INSERT INTO schedules(id,user_id,agent_id,cron,zone,prompt,enabled,created_at) VALUES(?,?,?,?,?,?,1,?)",
		id, uid, agentID, cron, zone, prompt, Now()); err != nil {
		return nil, err
	}
	return s.ScheduleByID(id)
}
func (s *Store) SetScheduleEnabled(id string, on bool) error {
	_, err := s.DB.Exec("UPDATE schedules SET enabled=? WHERE id=?", b2i(on), id)
	return err
}
func (s *Store) MarkScheduleRun(id string, t int64) error {
	_, err := s.DB.Exec("UPDATE schedules SET last_run_at=? WHERE id=?", t, id)
	return err
}
func (s *Store) DeleteSchedule(id string) error {
	_, err := s.DB.Exec("DELETE FROM schedules WHERE id=?", id)
	return err
}

func (s *Store) AddUsage(uid, agentID, model string, in, out int64, cost *float64) error {
	var c any
	if cost != nil {
		c = *cost
	}
	_, err := s.DB.Exec("INSERT INTO usage(user_id,agent_id,model,tokens_in,tokens_out,cost_usd,created_at) VALUES(?,?,?,?,?,?,?)", uid, agentID, model, in, out, c, Now())
	return err
}
func (s *Store) TokensSince(agentID string, since int64) (n int64, err error) {
	err = s.DB.QueryRow("SELECT COALESCE(SUM(tokens_in+tokens_out),0) FROM usage WHERE agent_id=? AND created_at>=?", agentID, since).Scan(&n)
	return
}

type UsageRow struct {
	AgentID string  `json:"agentId"`
	In      int64   `json:"tokensIn"`
	Out     int64   `json:"tokensOut"`
	Cost    float64 `json:"costUsd"`
}

func (s *Store) UsageSummary(uid string, since int64) ([]UsageRow, error) {
	rows, err := s.DB.Query("SELECT agent_id,SUM(tokens_in),SUM(tokens_out),COALESCE(SUM(cost_usd),0) FROM usage WHERE user_id=? AND created_at>=? GROUP BY agent_id", uid, since)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []UsageRow{}
	for rows.Next() {
		var u UsageRow
		if err := rows.Scan(&u.AgentID, &u.In, &u.Out, &u.Cost); err != nil {
			return nil, err
		}
		out = append(out, u)
	}
	return out, rows.Err()
}

func (s *Store) Audit(uid, agentID, action, details string) {
	if len(details) > 4000 {
		details = details[:4000]
	}
	var u, a any
	if uid != "" {
		u = uid
	}
	if agentID != "" {
		a = agentID
	}
	_, _ = s.DB.Exec("INSERT INTO audit_log(user_id,agent_id,action,details,created_at) VALUES(?,?,?,?,?)", u, a, action, details, Now())
}

type AuditRow struct {
	AgentID   string `json:"agentId,omitempty"`
	Action    string `json:"action"`
	Details   string `json:"details"`
	CreatedAt int64  `json:"createdAt"`
}

func (s *Store) RecentAudit(uid string, limit int) ([]AuditRow, error) {
	rows, err := s.DB.Query("SELECT agent_id,action,details,created_at FROM audit_log WHERE user_id=? ORDER BY id DESC LIMIT ?", uid, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := []AuditRow{}
	for rows.Next() {
		var r AuditRow
		var a sql.NullString
		if err := rows.Scan(&a, &r.Action, &r.Details, &r.CreatedAt); err != nil {
			return nil, err
		}
		r.AgentID = ns(a)
		out = append(out, r)
	}
	return out, rows.Err()
}

func (s *Store) RegisterDevice(uid, token string) error {
	if _, err := s.DB.Exec("DELETE FROM devices WHERE fcm_token=?", token); err != nil {
		return err
	}
	_, err := s.DB.Exec("INSERT INTO devices(id,user_id,fcm_token,created_at) VALUES(?,?,?,?)", NewID(), uid, token, Now())
	return err
}
