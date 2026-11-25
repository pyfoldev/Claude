package core

import (
	"context"
	"encoding/json"
	"log"
	"sync"

	"staika/server/internal/llm"
	"staika/server/internal/store"
)

// Perms хранится в agents.perms (JSON).
type Perms struct {
	Server      bool     `json:"server"`
	Browser     bool     `json:"browser"`
	Mail        bool     `json:"mail"`
	AlwaysAllow []string `json:"alwaysAllow"`
}

type AgentDTO struct {
	store.Agent
	Perms Perms `json:"perms"`
}

type MessageDTO struct {
	ID        string          `json:"id"`
	AgentID   string          `json:"agentId"`
	Sender    string          `json:"sender"`
	Type      string          `json:"type"`
	Content   json.RawMessage `json:"content"`
	CreatedAt int64           `json:"createdAt"`
}

// LLM — то, что нужно рантайму от слоя моделей (в тестах подменяется скриптом).
type LLM interface {
	Complete(ctx context.Context, u *store.User, modelID, system string, msgs []llm.Message, tools []llm.ToolSpec) (*llm.Result, *llm.ModelInfo, error)
}

type Push interface {
	Notify(userID, title, agentID string)
}

type LogPush struct{}

func (LogPush) Notify(userID, title, agentID string) {
	log.Printf("PUSH user=%s agent=%s title=%s", userID, agentID, title)
}

type Settings struct {
	WorkspacesDir string
	SandboxImage  string
}

type App struct {
	St   *store.Store
	Hub  *Hub
	LLM  LLM
	Push Push
	Set  Settings
	Sync bool // тесты: выполнять запуски агентов синхронно

	mu      sync.Mutex
	running map[string]bool
	dirty   map[string]bool
}

func NewApp(st *store.Store, hub *Hub, l LLM, set Settings) *App {
	return &App{St: st, Hub: hub, LLM: l, Push: LogPush{}, Set: set, running: map[string]bool{}, dirty: map[string]bool{}}
}

func (a *App) PermsOf(ag *store.Agent) Perms {
	var p Perms
	_ = json.Unmarshal([]byte(ag.Perms), &p)
	return p
}

func (a *App) AgentDTO(ag *store.Agent) AgentDTO { return AgentDTO{*ag, a.PermsOf(ag)} }

func (a *App) MessageDTO(m *store.Message) MessageDTO {
	return MessageDTO{m.ID, m.AgentID, m.Sender, m.Type, json.RawMessage(m.Content), m.CreatedAt}
}

// Post сохраняет сообщение в чат агента и рассылает событие клиентам.
func (a *App) Post(ag *store.Agent, sender, typ string, content map[string]any) *store.Message {
	b, _ := json.Marshal(content)
	m := &store.Message{ID: store.NewID(), AgentID: ag.ID, UserID: ag.UserID, Sender: sender, Type: typ, Content: string(b), CreatedAt: store.Now()}
	if err := a.St.InsertMessage(m); err != nil {
		log.Printf("insert message: %v", err)
		return m
	}
	str := func(k string) string { s, _ := content[k].(string); return s }
	preview := ""
	switch typ {
	case "text", "system":
		preview = str("text")
	case "approval":
		preview = "Нужно разрешение: " + str("title")
	case "doc":
		preview = "Файл: " + str("title")
	case "task":
		preview = "Задача: " + str("title")
	}
	if preview != "" {
		_ = a.St.SetAgentLast(ag.ID, preview, m.CreatedAt)
	}
	a.Hub.Publish(ag.UserID, "message.created", a.MessageDTO(m))
	if cur, _ := a.St.AgentByID(ag.ID); cur != nil {
		a.Hub.Publish(ag.UserID, "agent.updated", a.AgentDTO(cur))
	}
	return m
}

func (a *App) UpdateMessage(id string, content map[string]any) {
	m, _ := a.St.MessageByID(id)
	if m == nil {
		return
	}
	b, _ := json.Marshal(content)
	_ = a.St.UpdateMessage(id, string(b))
	m.Content = string(b)
	a.Hub.Publish(m.UserID, "message.updated", a.MessageDTO(m))
}

func (a *App) SetStatus(ag *store.Agent, status string) {
	_ = a.St.SetAgentStatus(ag.ID, status)
	if cur, _ := a.St.AgentByID(ag.ID); cur != nil {
		a.Hub.Publish(ag.UserID, "agent.updated", a.AgentDTO(cur))
	}
}
