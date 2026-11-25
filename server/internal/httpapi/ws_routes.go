package httpapi

import (
	"context"
	"log"
	"net/http"
	"time"

	"github.com/coder/websocket"

	"staika/server/internal/core"
)

func (s *Server) wsRoutes(m *http.ServeMux) {
	m.HandleFunc("GET /ws", s.eventsSocket)
	m.HandleFunc("GET /ws/dictate", s.dictationSocket)
	m.HandleFunc("GET /ws/call", s.callSocket)
}

// wsAuth: токен в query (?token=). Мобильное приложение не отправляет Origin, поэтому проверка Origin отключена,
// защита обеспечивается JWT.
func (s *Server) wsAuth(w http.ResponseWriter, r *http.Request) (*core.Principal, *websocket.Conn) {
	p, err := s.Auth.ParseAccess(r.URL.Query().Get("token"))
	if err != nil {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return nil, nil
	}
	c, err := websocket.Accept(w, r, &websocket.AcceptOptions{InsecureSkipVerify: true})
	if err != nil {
		return nil, nil
	}
	return p, c
}

func (s *Server) eventsSocket(w http.ResponseWriter, r *http.Request) {
	p, c := s.wsAuth(w, r)
	if c == nil {
		return
	}
	defer c.CloseNow()
	cl := &core.Client{UserID: p.UserID, Send: make(chan []byte, 64)}
	s.App.Hub.Add(cl)
	defer s.App.Hub.Remove(cl)
	ctx, cancel := context.WithCancel(r.Context())
	defer cancel()

	go func() { // читаем (ping и закрытие)
		defer cancel()
		for {
			typ, data, err := c.Read(ctx)
			if err != nil {
				return
			}
			if typ == websocket.MessageText && string(data) == "ping" {
				_ = c.Write(ctx, websocket.MessageText, []byte(`{"type":"pong","data":{}}`))
			}
		}
	}()
	_ = c.Write(ctx, websocket.MessageText, []byte(`{"type":"hello","data":{}}`))
	keep := time.NewTicker(25 * time.Second)
	defer keep.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case b := <-cl.Send:
			wctx, wc := context.WithTimeout(ctx, 10*time.Second)
			err := c.Write(wctx, websocket.MessageText, b)
			wc()
			if err != nil {
				return
			}
		case <-keep.C:
			pctx, pc := context.WithTimeout(ctx, 10*time.Second)
			err := c.Ping(pctx)
			pc()
			if err != nil {
				return
			}
		}
	}
}

var _ = log.Printf
