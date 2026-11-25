package store

type User struct {
	ID            string `json:"id"`
	Email         string `json:"email"`
	Name          string `json:"name"`
	PasswordHash  string `json:"-"`
	GoogleSub     string `json:"-"`
	Role          string `json:"role"`
	EmailVerified bool   `json:"emailVerified"`
	CreatedAt     int64  `json:"-"`
}

func (u *User) IsOwner() bool { return u.Role == "owner" }

// CanUseServerKeys: серверные ключи провайдеров доступны только owner и family, остальным нужны свои.
func (u *User) CanUseServerKeys() bool { return u.Role == "owner" || u.Role == "family" }
func (u *User) CanUseShell() bool      { return u.Role == "owner" }

type Agent struct {
	ID         string `json:"id"`
	UserID     string `json:"-"`
	ParentID   string `json:"parentId,omitempty"`
	Name       string `json:"name"`
	RoleDesc   string `json:"role"`
	Pal        string `json:"pal"`
	Model      string `json:"model"`
	Chief      bool   `json:"chief"`
	Perms      string `json:"-"`
	Status     string `json:"status"`
	LastText   string `json:"lastText"`
	LastAt     int64  `json:"lastAt"`
	TokenLimit int64  `json:"-"`
	CreatedAt  int64  `json:"-"`
}

type Message struct {
	ID        string `json:"id"`
	AgentID   string `json:"agentId"`
	UserID    string `json:"-"`
	Sender    string `json:"sender"`
	Type      string `json:"type"`
	Content   string `json:"-"`
	CreatedAt int64  `json:"createdAt"`
}

type Approval struct {
	ID         string `json:"id"`
	UserID     string `json:"-"`
	AgentID    string `json:"agentId"`
	MessageID  string `json:"-"`
	ToolCallID string `json:"-"`
	ToolName   string `json:"tool"`
	Args       string `json:"-"`
	Summary    string `json:"summary"`
	Risk       string `json:"risk"`
	Status     string `json:"status"`
	CreatedAt  int64  `json:"createdAt"`
}

type Task struct {
	ID        string  `json:"id"`
	UserID    string  `json:"-"`
	FromAgent string  `json:"fromAgent,omitempty"`
	ToAgent   string  `json:"toAgent"`
	Title     string  `json:"title"`
	Status    string  `json:"status"`
	Progress  float64 `json:"progress"`
	Result    string  `json:"result,omitempty"`
	CreatedAt int64   `json:"createdAt"`
	UpdatedAt int64   `json:"updatedAt"`
}

type Schedule struct {
	ID        string `json:"id"`
	UserID    string `json:"-"`
	AgentID   string `json:"agentId"`
	Cron      string `json:"cron"`
	Zone      string `json:"zone"`
	Prompt    string `json:"prompt"`
	Enabled   bool   `json:"enabled"`
	LastRunAt int64  `json:"lastRunAt,omitempty"`
	CreatedAt int64  `json:"createdAt"`
}

type TranscriptRow struct {
	ID      int64
	AgentID string
	Role    string
	Content string
}
