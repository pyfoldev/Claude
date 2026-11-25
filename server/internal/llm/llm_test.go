package llm

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func tc(id, name string) ToolCall {
	return ToolCall{ID: id, Name: name, Args: json.RawMessage(`{"a":1}`)}
}

func TestAnthropicGroupsToolResultsInOneUserMessage(t *testing.T) {
	msgs := []Message{
		{Role: "user", Text: "q"},
		{Role: "assistant", ToolCalls: []ToolCall{tc("a", "x"), tc("b", "y")}},
		{Role: "tool", ToolCallID: "a", Text: "ra"},
		{Role: "tool", ToolCallID: "b", Text: "rb"},
	}
	body, err := Anthropic{}.BuildBody("m", "sys", msgs, []ToolSpec{{Name: "x", Description: "d", Schema: json.RawMessage(`{"type":"object"}`)}}, 100)
	if err != nil {
		t.Fatal(err)
	}
	var v struct {
		Messages []struct {
			Role    string            `json:"role"`
			Content []json.RawMessage `json:"content"`
		} `json:"messages"`
	}
	_ = json.Unmarshal(body, &v)
	// user(строка) нельзя разобрать как массив, поэтому проверяем последние два
	n := len(v.Messages)
	if n != 3 || v.Messages[2].Role != "user" || len(v.Messages[2].Content) != 2 {
		t.Fatalf("результаты инструментов должны быть в одном user-сообщении: %s", body)
	}
	if !strings.Contains(string(body), `"tool_use_id":"a"`) || !strings.Contains(string(body), `"input_schema"`) {
		t.Fatalf("неверный формат: %s", body)
	}
}

func TestAnthropicParse(t *testing.T) {
	r, err := Anthropic{}.Parse([]byte(`{"content":[{"type":"text","text":"привет"},{"type":"tool_use","id":"t1","name":"fs_list","input":{"path":"."}}],"stop_reason":"tool_use","usage":{"input_tokens":7,"output_tokens":3}}`))
	if err != nil || r.Text != "привет" || len(r.ToolCalls) != 1 || r.ToolCalls[0].Name != "fs_list" || r.TokensIn != 7 || r.TokensOut != 3 {
		t.Fatalf("%+v %v", r, err)
	}
}

func TestOpenAIBodyAndParse(t *testing.T) {
	msgs := []Message{
		{Role: "user", Text: "q"},
		{Role: "assistant", ToolCalls: []ToolCall{tc("a", "x")}},
		{Role: "tool", ToolCallID: "a", Text: "ra"},
	}
	body, _ := OpenAICompat{}.BuildBody("m", "sys", msgs, []ToolSpec{{Name: "x", Schema: json.RawMessage(`{"type":"object"}`)}}, 50)
	s := string(body)
	for _, want := range []string{`"role":"system"`, `"tool_calls"`, `"tool_call_id":"a"`, `"tool_choice":"auto"`, `"arguments":"{\"a\":1}"`} {
		if !strings.Contains(s, want) {
			t.Fatalf("нет %s в %s", want, s)
		}
	}
	r, err := OpenAICompat{}.Parse([]byte(`{"choices":[{"message":{"content":null,"tool_calls":[{"id":"c1","function":{"name":"x","arguments":"{\"p\":2}"}}]},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":4,"completion_tokens":2}}`))
	if err != nil || len(r.ToolCalls) != 1 || string(r.ToolCalls[0].Args) != `{"p":2}` || r.TokensIn != 4 {
		t.Fatalf("%+v %v", r, err)
	}
	// битые аргументы не ломают разбор
	r, err = OpenAICompat{}.Parse([]byte(`{"choices":[{"message":{"content":"ok","tool_calls":[{"id":"c1","function":{"name":"x","arguments":"{oops"}}]}}]}`))
	if err != nil || string(r.ToolCalls[0].Args) != "{}" {
		t.Fatalf("%+v %v", r, err)
	}
}

func TestOpenAICompatEndToEndAgainstFakeRiver(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		if r.URL.Path != "/v1/chat/completions" || r.Header.Get("Authorization") != "Bearer rv_key" || !strings.Contains(string(b), "DeepSeek") {
			http.Error(w, "bad request", 400)
			return
		}
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"привет от River"},"finish_reason":"stop"}],"usage":{"prompt_tokens":3,"completion_tokens":4}}`))
	}))
	defer srv.Close()
	res, err := OpenAICompat{}.Complete(context.Background(), "deepseek-ai/DeepSeek-V4.1-Flash", srv.URL+"/v1", "rv_key", "sys", []Message{{Role: "user", Text: "hi"}}, nil, 100)
	if err != nil || res.Text != "привет от River" {
		t.Fatalf("%+v %v", res, err)
	}
	// ошибка провайдера возвращается как *Error со статусом
	_, err = OpenAICompat{}.Complete(context.Background(), "x", srv.URL+"/v1", "wrong", "sys", []Message{{Role: "user", Text: "hi"}}, nil, 100)
	if e, ok := err.(*Error); !ok || e.Status != 400 {
		t.Fatalf("ожидали *Error 400, получили %v", err)
	}
}

func TestCatalog(t *testing.T) {
	if Find("Claude Haiku 4.5") == nil || Find("Claude Haiku 4.5").APIModel != "claude-haiku-4-5" {
		t.Fatal("Haiku 4.5 должен быть в каталоге с ID claude-haiku-4-5")
	}
	if Find("DeepSeek V4.1 Flash").BaseURL != "https://api.river.ai/v1" {
		t.Fatal("River base URL")
	}
}
