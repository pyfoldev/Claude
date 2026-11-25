package llm

import (
	"context"
	"encoding/json"
	"strings"
)

// Anthropic — нативный Messages API с tool use.
type Anthropic struct{}

func (Anthropic) ID() string { return "anthropic" }

type aBlock struct {
	Type      string          `json:"type"`
	Text      string          `json:"text,omitempty"`
	ID        string          `json:"id,omitempty"`
	Name      string          `json:"name,omitempty"`
	Input     json.RawMessage `json:"input,omitempty"`
	ToolUseID string          `json:"tool_use_id,omitempty"`
	Content   string          `json:"content,omitempty"`
}
type aMsg struct {
	Role    string `json:"role"`
	Content any    `json:"content"`
}

func (Anthropic) BuildBody(model, system string, msgs []Message, tools []ToolSpec, maxTokens int) ([]byte, error) {
	out := []aMsg{}
	for i := 0; i < len(msgs); {
		m := msgs[i]
		switch m.Role {
		case "user":
			out = append(out, aMsg{"user", m.Text})
			i++
		case "assistant":
			blocks := []aBlock{}
			if strings.TrimSpace(m.Text) != "" {
				blocks = append(blocks, aBlock{Type: "text", Text: m.Text})
			}
			for _, c := range m.ToolCalls {
				in := c.Args
				if len(in) == 0 {
					in = json.RawMessage("{}")
				}
				blocks = append(blocks, aBlock{Type: "tool_use", ID: c.ID, Name: c.Name, Input: in})
			}
			if len(blocks) == 0 {
				blocks = append(blocks, aBlock{Type: "text", Text: "…"})
			}
			out = append(out, aMsg{"assistant", blocks})
			i++
		default: // подряд идущие результаты инструментов — одно user-сообщение
			blocks := []aBlock{}
			for i < len(msgs) && msgs[i].Role == "tool" {
				blocks = append(blocks, aBlock{Type: "tool_result", ToolUseID: msgs[i].ToolCallID, Content: msgs[i].Text})
				i++
			}
			out = append(out, aMsg{"user", blocks})
		}
	}
	body := map[string]any{"model": model, "max_tokens": maxTokens, "system": system, "messages": out}
	if len(tools) > 0 {
		ts := []map[string]any{}
		for _, t := range tools {
			ts = append(ts, map[string]any{"name": t.Name, "description": t.Description, "input_schema": json.RawMessage(t.Schema)})
		}
		body["tools"] = ts
	}
	return json.Marshal(body)
}

func (Anthropic) Parse(data []byte) (*Result, error) {
	var r struct {
		Content    []aBlock `json:"content"`
		StopReason string   `json:"stop_reason"`
		Usage      struct {
			In  int `json:"input_tokens"`
			Out int `json:"output_tokens"`
		} `json:"usage"`
	}
	if err := json.Unmarshal(data, &r); err != nil {
		return nil, &Error{Msg: "Некорректный ответ Anthropic"}
	}
	res := &Result{TokensIn: r.Usage.In, TokensOut: r.Usage.Out, Stop: r.StopReason}
	var sb strings.Builder
	for _, b := range r.Content {
		switch b.Type {
		case "text":
			sb.WriteString(b.Text)
		case "tool_use":
			in := b.Input
			if len(in) == 0 {
				in = json.RawMessage("{}")
			}
			res.ToolCalls = append(res.ToolCalls, ToolCall{ID: b.ID, Name: b.Name, Args: in})
		}
	}
	res.Text = sb.String()
	return res, nil
}

func (a Anthropic) Complete(ctx context.Context, model, baseURL, key, system string, msgs []Message, tools []ToolSpec, maxTokens int) (*Result, error) {
	body, err := a.BuildBody(model, system, msgs, tools, maxTokens)
	if err != nil {
		return nil, err
	}
	data, err := postJSON(ctx, strings.TrimRight(baseURL, "/")+"/v1/messages",
		map[string]string{"x-api-key": key, "anthropic-version": "2023-06-01"}, body, "Anthropic")
	if err != nil {
		return nil, err
	}
	return a.Parse(data)
}
