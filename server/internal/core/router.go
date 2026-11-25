package core

import (
	"context"
	"fmt"

	"staika/server/internal/llm"
	"staika/server/internal/store"
)

// Router выбирает провайдера и ключ: свой ключ пользователя, иначе серверный (только owner/family).
type Router struct {
	St        *store.Store
	Box       *SecretBox
	Server    map[string]string // keyName -> серверный ключ
	Providers map[string]llm.Provider
}

func NewRouter(st *store.Store, box *SecretBox, server map[string]string) *Router {
	r := &Router{St: st, Box: box, Server: server, Providers: map[string]llm.Provider{}}
	for _, p := range []llm.Provider{llm.Anthropic{}, llm.OpenAICompat{}} {
		r.Providers[p.ID()] = p
	}
	return r
}

func (r *Router) ResolveKey(u *store.User, keyName string) string {
	if c, _ := r.St.GetKey(u.ID, keyName); c != "" {
		if k, err := r.Box.Open(c); err == nil {
			return k
		}
	}
	if u.CanUseServerKeys() {
		return r.Server[keyName]
	}
	return ""
}

func (r *Router) Complete(ctx context.Context, u *store.User, modelID, system string, msgs []llm.Message, tools []llm.ToolSpec) (*llm.Result, *llm.ModelInfo, error) {
	info := llm.Find(modelID)
	if info == nil {
		return nil, nil, &llm.Error{Msg: "Неизвестная модель: " + modelID}
	}
	key := r.ResolveKey(u, info.KeyName)
	if key == "" {
		return nil, info, &llm.Error{Msg: fmt.Sprintf("Нет ключа %s. Добавьте свой ключ в настройках провайдеров.", info.KeyName)}
	}
	p := r.Providers[info.Provider]
	if p == nil {
		return nil, info, &llm.Error{Msg: "Провайдер недоступен: " + info.Provider}
	}
	res, err := p.Complete(ctx, info.APIModel, info.BaseURL, key, system, msgs, tools, 4096)
	return res, info, err
}
