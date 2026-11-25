package llm

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"time"
)

var client = &http.Client{Timeout: 3 * time.Minute}

func postJSON(ctx context.Context, url string, headers map[string]string, body []byte, who string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, &Error{Msg: "bad request: " + err.Error()}
	}
	req.Header.Set("content-type", "application/json")
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, &Error{Msg: "Нет связи с " + who + ": " + err.Error()}
	}
	defer resp.Body.Close()
	data, _ := io.ReadAll(io.LimitReader(resp.Body, 8<<20))
	if resp.StatusCode < 200 || resp.StatusCode > 299 {
		s := string(data)
		if len(s) > 300 {
			s = s[:300]
		}
		return nil, &Error{Msg: who + " " + resp.Status + ": " + s, Status: resp.StatusCode}
	}
	return data, nil
}
