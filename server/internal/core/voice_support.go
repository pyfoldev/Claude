package core

import (
	"encoding/json"

	"staika/server/internal/llm"
	"staika/server/internal/store"
)

// SystemPrompt нужен голосовому мосту (Settings.agent.think.prompt).
func (a *App) SystemPrompt(ag *store.Agent, u *store.User) string { return a.systemPrompt(ag, u) }

// ExecVoiceTool выполняет безопасный инструмент по вызову из голосового разговора.
// Рискованные инструменты (отправка, система, удаление) из голоса недоступны: их нельзя подтвердить на лету.
func (a *App) ExecVoiceTool(ag *store.Agent, u *store.User, name string, args Args) string {
	t := a.toolByName(name)
	tc, err := a.toolCtx(ag, u)
	if t == nil || err != nil || !t.available(tc) || t.Risk > RiskWriteLocal {
		return "Эта функция недоступна"
	}
	raw, _ := json.Marshal(args)
	return a.safeExecute(t, tc, llm.ToolCall{ID: "voice", Name: name, Args: raw}, args)
}
