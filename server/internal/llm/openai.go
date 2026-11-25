package llm

import (
	"context"
	"encoding/json"
	"strings"
)

// OpenAICompat — Chat Completions: OpenAI, River (api.river.ai/v1), Gemini (OpenAI-совместимый) и т.д.
type OpenAICompat struct{}

func (OpenAICompat) ID() string { return "openai-compat" }

func (OpenAICompat) BuildBody(model, system string, msgs []Message, tools []ToolSpec, maxTokens int) ([]byte, error) {
	ms := []map[string]any{{"role": "system", "content": system}}
	for _, m := range msgs {
		switch m.Role {
		case "user":
			ms = append(ms, map[string]any{"role": "user", "content": m.Text})
		case "assistant":
			o := map[string]any{"role": "assistant"}
			if strings.TrimSpace(m.Text) == "" {
				o["content"] = nil
			} else {
				o["content"] = m.Text
			}
			if len(m.ToolCalls) > 0 {
				tcs := []map[string]any{}
				for _, c := range m.ToolCalls {
					args := string(c.Args)
					if args == "" {
						args = "{}"
					}
					tcs = append(tcs, map[string]any{"id": c.ID, "type": "function", "function": map[string]any{"name": c.Name, "arguments": args}})
				}
				o["tool_calls"] = tcs
			}
			ms = append(ms, o)
		default:
			ms = append(ms, map[string]any{"role": "tool", "tool_call_id": m.ToolCallID, "content": m.Text})
		}
	}
	body := map[string]any{"model": model, "max_tokens": maxTokens, "messages": ms}
	if len(tools) > 0 {
		ts := []map[string]any{}
		for _, t := range tools {
			ts = append(ts, map[string]any{"type": "function", "function": map[string]any{"name": t.Name, "description": t.Description, "parameters": json.RawMessage(t.Schema)}})
		}
		body["tools"] = ts
		body["tool_choice"] = "auto"
	}
	return json.Marshal(body)
}

func (OpenAICompat) Parse(data []byte) (*Result, error) {
	var r struct {
		Choices []struct {
			Message struct {
				Content   *string `json:"content"`
				ToolCalls []struct {
					ID       string `json:"id"`
					Function struct {
						Name      string `json:"name"`
						Arguments string `json:"arguments"`
					} `json:"function"`
				} `json:"tool_calls"`
			} `json:"message"`
			FinishReason string `json:"finish_reason"`
		} `json:"choices"`
		Usage struct {
			In  int `json:"prompt_tokens"`
			Out int `json:"completion_tokens"`
		} `json:"usage"`
	}
	if err := json.Unmarshal(data, &r); err != nil || len(r.Choices) == 0 {
		return nil, &Error{Msg: "Пустой или некорректный ответ модели"}
	}
	c := r.Choices[0]
	res := &Result{TokensIn: r.Usage.In, TokensOut: r.Usage.Out, Stop: c.FinishReason}
	if c.Message.Content != nil {
		res.Text = *c.Message.Content
	}
	for _, tc := range c.Message.ToolCalls {
		args := json.RawMessage(strings.TrimSpace(tc.Function.Arguments))
		if len(args) == 0 || !json.Valid(args) {
			args = json.RawMessage("{}")
		}
		res.ToolCalls = append(res.ToolCalls, ToolCall{ID: tc.ID, Name: tc.Function.Name, Args: args})
	}
	return res, nil
}

func (o OpenAICompat) Complete(ctx context.Context, model, baseURL, key, system string, msgs []Message, tools []ToolSpec, maxTokens int) (*Result, error) {
	body, err := o.BuildBody(model, system, msgs, tools, maxTokens)
	if err != nil {
		return nil, err
	}
	data, err := postJSON(ctx, strings.TrimRight(baseURL, "/")+"/chat/completions", map[string]string{"Authorization": "Bearer " + key}, body, "провайдер")
	if err != nil {
		return nil, err
	}
	return o.Parse(data)
}
