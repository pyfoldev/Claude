package httpapi

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/coder/websocket"

	"staika/server/internal/core"
	"staika/server/internal/llm"
	"staika/server/internal/store"
)

const (
	deepgramListen = "wss://api.deepgram.com/v1/listen"
	deepgramAgent  = "wss://agent.deepgram.com/v1/agent/converse"
)

var langRe = regexp.MustCompile(`^[a-zA-Z-]{2,8}$`)

func logDialFail(what string, err error, resp *http.Response) {
	status := 0
	if resp != nil {
		status = resp.StatusCode
	}
	log.Printf("voice: %s upstream dial failed: %v (HTTP %d)", what, err, status)
}

// deepgramKey: свой ключ пользователя, иначе серверный только для owner/family (иначе чужие минуты оплачивает владелец).
func (s *Server) deepgramKey(p *core.Principal) (*store.User, string) {
	u, _ := s.St.UserByID(p.UserID)
	if u == nil {
		return nil, ""
	}
	return u, s.Router.ResolveKey(u, "deepgram")
}

// relay соединяет клиента и Deepgram. onUpstreamText может перехватить текстовое сообщение (true = не пересылать).
func relay(ctx context.Context, client, up *websocket.Conn, onUpstreamText func(typ websocket.MessageType, data []byte) bool, send func(ctx context.Context, data []byte) error) {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	client.SetReadLimit(1 << 20)
	up.SetReadLimit(4 << 20)
	var wg sync.WaitGroup
	wg.Add(2)
	go func() { // клиент -> Deepgram
		defer wg.Done()
		defer cancel()
		for {
			typ, data, err := client.Read(ctx)
			if err != nil {
				return
			}
			if send != nil && typ == websocket.MessageText {
				_ = send(ctx, data)
				continue
			}
			if err := up.Write(ctx, typ, data); err != nil {
				return
			}
		}
	}()
	go func() { // Deepgram -> клиент
		defer wg.Done()
		defer cancel()
		for {
			typ, data, err := up.Read(ctx)
			if err != nil {
				return
			}
			if typ == websocket.MessageText && onUpstreamText != nil && onUpstreamText(typ, data) {
				continue
			}
			if err := client.Write(ctx, typ, data); err != nil {
				return
			}
		}
	}()
	<-ctx.Done()
	client.CloseNow()
	up.CloseNow()
	wg.Wait()
}

// Диктовка: PCM linear16 16 кГц от клиента -> Deepgram Nova-3 -> JSON с промежуточным и финальным текстом.
func (s *Server) dictationSocket(w http.ResponseWriter, r *http.Request) {
	p, c := s.wsAuth(w, r)
	if c == nil {
		return
	}
	_, key := s.deepgramKey(p)
	if key == "" {
		log.Printf("voice: dictation denied for user %s: no Deepgram key (set DEEPGRAM_API_KEY or add own key)", p.UserID)
		c.Close(websocket.StatusPolicyViolation, "voice_not_available")
		return
	}
	lang := r.URL.Query().Get("lang")
	if !langRe.MatchString(lang) {
		lang = "ru"
	}
	q := url.Values{"model": {"nova-3"}, "language": {lang}, "encoding": {"linear16"}, "sample_rate": {"16000"}, "channels": {"1"},
		"interim_results": {"true"}, "smart_format": {"true"}, "punctuate": {"true"}, "endpointing": {"400"}}
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Minute)
	defer cancel()
	up, resp, err := websocket.Dial(ctx, deepgramListen+"?"+q.Encode(), &websocket.DialOptions{HTTPHeader: http.Header{"Authorization": {"Token " + key}}})
	if err != nil {
		logDialFail("dictation", err, resp)
		c.Close(websocket.StatusInternalError, "upstream_unavailable")
		return
	}
	relay(ctx, c, up, nil, nil)
}

// Звонок: мост к Deepgram Voice Agent. Сервер отправляет Settings, обрабатывает функции и сохраняет расшифровку в чат.
func (s *Server) callSocket(w http.ResponseWriter, r *http.Request) {
	p, c := s.wsAuth(w, r)
	if c == nil {
		return
	}
	user, key := s.deepgramKey(p)
	ag, _ := s.St.AgentByID(r.URL.Query().Get("agentId"))
	if key == "" || user == nil {
		log.Printf("voice: call denied for user %s: no Deepgram key (set DEEPGRAM_API_KEY or add own key)", p.UserID)
		c.Close(websocket.StatusPolicyViolation, "voice_not_available")
		return
	}
	if ag == nil || ag.UserID != p.UserID {
		c.Close(websocket.StatusPolicyViolation, "agent_not_found")
		return
	}
	lang := r.URL.Query().Get("lang")
	if !langRe.MatchString(lang) {
		lang = "ru"
	}
	model := r.URL.Query().Get("model")
	if model == "" {
		model = "Claude Haiku 4.5"
	}
	ctx, cancel := context.WithTimeout(r.Context(), 60*time.Minute)
	defer cancel()
	up, resp, err := websocket.Dial(ctx, deepgramAgent, &websocket.DialOptions{HTTPHeader: http.Header{"Authorization": {"Token " + key}}})
	if err != nil {
		logDialFail("call", err, resp)
		c.Close(websocket.StatusInternalError, "upstream_unavailable")
		return
	}
	start := time.Now()
	var mu sync.Mutex
	var lines []string
	wr := func(data []byte) { _ = up.Write(ctx, websocket.MessageText, data) }

	onText := func(_ websocket.MessageType, data []byte) bool {
		var n struct {
			Type      string `json:"type"`
			Role      string `json:"role"`
			Content   string `json:"content"`
			Functions []struct {
				ID, Name, Arguments string
				ClientSide          *bool `json:"client_side"`
			} `json:"functions"`
		}
		if json.Unmarshal(data, &n) != nil {
			return false
		}
		switch n.Type {
		case "Welcome":
			st, err := s.voiceSettings(user, ag, model, lang)
			if err == nil {
				wr(st)
			}
		case "ConversationText":
			who := "Агент"
			if n.Role == "user" {
				who = "Вы"
			}
			mu.Lock()
			lines = append(lines, who+": "+n.Content)
			mu.Unlock()
		case "FunctionCallRequest":
			for _, f := range n.Functions {
				if f.ClientSide != nil && !*f.ClientSide {
					continue
				}
				tool := map[string]string{"get_status": "list_team", "delegate_to_team": "delegate_task"}[f.Name]
				if tool == "" {
					tool = f.Name
				}
				args := core.Args{}
				_ = json.Unmarshal([]byte(f.Arguments), &args)
				out := s.App.ExecVoiceTool(ag, user, tool, args)
				b, _ := json.Marshal(map[string]any{"type": "FunctionCallResponse", "id": f.ID, "name": f.Name, "content": out})
				wr(b)
			}
			return true
		}
		return false
	}
	relay(ctx, c, up, onText, nil)

	// после разговора: расшифровка в чат и в контекст агента
	mu.Lock()
	defer mu.Unlock()
	secs := int(time.Since(start).Seconds())
	s.St.Audit(user.ID, ag.ID, "voice_call", fmt.Sprintf("seconds=%d", secs))
	if len(lines) > 0 {
		body := fmt.Sprintf("Звонок %d:%02d\n%s", secs/60, secs%60, strings.Join(lines, "\n"))
		if r := []rune(body); len(r) > 6000 {
			body = string(r[:6000])
		}
		s.App.Post(ag, "system", "system", map[string]any{"text": body})
		s.App.AddUserMessageToContext(ag.ID, "[Расшифровка голосового разговора с пользователем]\n"+body)
	}
}

// voiceSettings строит Settings для Deepgram Voice Agent.
func (s *Server) voiceSettings(u *store.User, ag *store.Agent, modelID, lang string) ([]byte, error) {
	listenModel := "flux-general-multi"
	if strings.HasPrefix(lang, "en") {
		listenModel = "flux-general-en"
	}
	think := s.voiceThink(u, modelID)
	think["prompt"] = s.App.SystemPrompt(ag, u) + "\nЭто голосовой разговор: отвечайте коротко и естественно, без списков и разметки. Долгую работу поручайте через функции."
	str := map[string]any{"type": "string"}
	think["functions"] = []map[string]any{
		{"name": "get_status", "description": "Узнать список агентов команды и их статусы", "parameters": map[string]any{"type": "object", "properties": map[string]any{}}},
		{"name": "delegate_to_team", "description": "Поручить задачу агенту команды; результат придёт в чат",
			"parameters": map[string]any{"type": "object", "properties": map[string]any{"agent": str, "task": str}, "required": []string{"agent", "task"}}},
		{"name": "remember", "description": "Запомнить важный факт",
			"parameters": map[string]any{"type": "object", "properties": map[string]any{"text": str}, "required": []string{"text"}}},
	}
	agent := map[string]any{
		"listen":   map[string]any{"provider": map[string]any{"type": "deepgram", "version": "v2", "model": listenModel}},
		"think":    think,
		"greeting": "Привет! Слушаю вас.",
	}
	// Голос (например, «Владимир») задаётся готовым JSON: ID модели нужно проверить в Deepgram при первом запуске.
	if s.Cfg.VoiceSpeakJSON != "" {
		var sp any
		if err := json.Unmarshal([]byte(s.Cfg.VoiceSpeakJSON), &sp); err == nil {
			agent["speak"] = sp
		}
	}
	return json.Marshal(map[string]any{
		"type": "Settings",
		"audio": map[string]any{
			"input":  map[string]any{"encoding": "linear16", "sample_rate": 16000},
			"output": map[string]any{"encoding": "linear16", "sample_rate": 24000, "container": "none"},
		},
		"agent": agent,
	})
}

// voiceThink: управляемые модели Deepgram (без ключа) либо свой endpoint (River и др.).
func (s *Server) voiceThink(u *store.User, modelID string) map[string]any {
	info := llm.Find(modelID)
	if info == nil {
		info = llm.Find("Claude Haiku 4.5")
	}
	think := map[string]any{}
	switch info.KeyName {
	case "anthropic":
		m := info.APIModel
		if m == "claude-sonnet-5-5" {
			m = "claude-sonnet-5" // в списке управляемых моделей Deepgram
		}
		think["provider"] = map[string]any{"type": "anthropic", "model": m}
	case "openai":
		think["provider"] = map[string]any{"type": "open_ai", "model": info.APIModel}
	case "google":
		think["provider"] = map[string]any{"type": "google", "model": info.APIModel}
	default:
		think["provider"] = map[string]any{"type": "open_ai", "model": info.APIModel}
		if k := s.Router.ResolveKey(u, info.KeyName); k != "" {
			think["endpoint"] = map[string]any{"url": strings.TrimRight(info.BaseURL, "/") + "/chat/completions",
				"headers": map[string]string{"authorization": "Bearer " + k}}
		}
	}
	return think
}
