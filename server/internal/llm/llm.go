// Package llm: единый интерфейс к моделям (Anthropic, OpenAI-совместимые: OpenAI, River, Gemini и др.).
package llm

import (
	"context"
	"encoding/json"
)

type ToolCall struct {
	ID   string          `json:"id"`
	Name string          `json:"name"`
	Args json.RawMessage `json:"args"`
}

// Message — запись контекста: role = user | assistant | tool.
type Message struct {
	Role       string
	Text       string
	ToolCalls  []ToolCall
	ToolCallID string
	ToolName   string
}

type ToolSpec struct {
	Name        string
	Description string
	Schema      json.RawMessage
}

type Result struct {
	Text      string
	ToolCalls []ToolCall
	TokensIn  int
	TokensOut int
	Stop      string
}

type Error struct {
	Msg    string
	Status int
}

func (e *Error) Error() string { return e.Msg }

type Provider interface {
	ID() string
	Complete(ctx context.Context, model, baseURL, apiKey, system string, msgs []Message, tools []ToolSpec, maxTokens int) (*Result, error)
}

type ModelInfo struct {
	ID       string  `json:"id"`
	Label    string  `json:"label"`
	Provider string  `json:"-"` // anthropic | openai-compat
	KeyName  string  `json:"provider"`
	APIModel string  `json:"-"`
	BaseURL  string  `json:"-"`
	PriceIn  float64 `json:"-"` // $ за 1M токенов; 0 = неизвестно
	PriceOut float64 `json:"-"`
}

const (
	openaiURL    = "https://api.openai.com/v1"
	googleURL    = "https://generativelanguage.googleapis.com/v1beta/openai"
	riverURL     = "https://api.river.ai/v1"
	anthropicURL = "https://api.anthropic.com"
)

// Catalog: цены указаны только там, где они подтверждены документацией (River).
var Catalog = []ModelInfo{
	{ID: "Claude Sonnet 5.5", Label: "Claude Sonnet 5.5", Provider: "anthropic", KeyName: "anthropic", APIModel: "claude-sonnet-5-5", BaseURL: anthropicURL},
	{ID: "Claude Haiku 4.5", Label: "Claude Haiku 4.5", Provider: "anthropic", KeyName: "anthropic", APIModel: "claude-haiku-4-5", BaseURL: anthropicURL},
	{ID: "GPT-5.5", Label: "GPT-5.5", Provider: "openai-compat", KeyName: "openai", APIModel: "gpt-5.5", BaseURL: openaiURL},
	{ID: "Gemini 3.5 Flash", Label: "Gemini 3.5 Flash", Provider: "openai-compat", KeyName: "google", APIModel: "gemini-3.5-flash", BaseURL: googleURL},
	{ID: "DeepSeek V4.1 Flash", Label: "DeepSeek V4.1 Flash (River)", Provider: "openai-compat", KeyName: "river", APIModel: "deepseek-ai/DeepSeek-V4.1-Flash", BaseURL: riverURL, PriceIn: 0.12, PriceOut: 0.48},
	{ID: "Kimi K3", Label: "Kimi K3 (River)", Provider: "openai-compat", KeyName: "river", APIModel: "moonshotai/Kimi-K3", BaseURL: riverURL},
	{ID: "GLM-5.3", Label: "GLM-5.3 (River)", Provider: "openai-compat", KeyName: "river", APIModel: "zai-org/GLM-5.3", BaseURL: riverURL, PriceIn: 1.12, PriceOut: 3.52},
	{ID: "GLM-5.3 Flash", Label: "GLM-5.3 Flash (River)", Provider: "openai-compat", KeyName: "river", APIModel: "zai-org/GLM-5.3-Flash", BaseURL: riverURL, PriceIn: 0.12, PriceOut: 0.40},
}

func Find(id string) *ModelInfo {
	for i := range Catalog {
		if Catalog[i].ID == id {
			return &Catalog[i]
		}
	}
	return nil
}
