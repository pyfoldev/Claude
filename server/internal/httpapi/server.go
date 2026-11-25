// Package httpapi: REST, WebSocket и голосовые мосты.
package httpapi

import (
	"encoding/json"
	"errors"
	"io"
	"log"
	"net"
	"net/http"
	"strings"

	"staika/server/internal/config"
	"staika/server/internal/core"
	"staika/server/internal/store"
)

type Server struct {
	App        *core.App
	Auth       *core.Auth
	St         *store.Store
	Router     *core.Router
	Box        *core.SecretBox
	Limiter    *core.RateLimiter
	Cfg        config.Config
	TrustProxy bool
}

type handler func(w http.ResponseWriter, r *http.Request)
type authed func(w http.ResponseWriter, r *http.Request, p *core.Principal)

func (s *Server) writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func (s *Server) fail(w http.ResponseWriter, err error) {
	var ae *core.APIError
	if errors.As(err, &ae) {
		s.writeJSON(w, ae.Status, map[string]string{"error": ae.Code, "message": ae.Message})
		return
	}
	log.Printf("internal error: %v", err)
	s.writeJSON(w, 500, map[string]string{"error": "internal", "message": "Внутренняя ошибка"})
}

func (s *Server) ip(r *http.Request) string {
	if s.TrustProxy {
		if x := strings.TrimSpace(strings.Split(r.Header.Get("X-Forwarded-For"), ",")[0]); x != "" {
			return x
		}
	}
	h, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return h
}

func (s *Server) decode(w http.ResponseWriter, r *http.Request, v any) bool {
	if err := json.NewDecoder(io.LimitReader(r.Body, 1<<20)).Decode(v); err != nil && !errors.Is(err, io.EOF) {
		s.fail(w, core.BadRequest("bad_json", "Некорректный запрос"))
		return false
	}
	return true
}

func (s *Server) open(h handler) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) { h(w, r) }
}

func (s *Server) secure(h authed) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		hd := r.Header.Get("Authorization")
		if !strings.HasPrefix(hd, "Bearer ") {
			s.fail(w, core.Unauthorized("Требуется вход"))
			return
		}
		p, err := s.Auth.ParseAccess(strings.TrimSpace(strings.TrimPrefix(hd, "Bearer ")))
		if err != nil {
			s.fail(w, err)
			return
		}
		h(w, r, p)
	}
}

func (s *Server) user(p *core.Principal) (*store.User, error) {
	u, err := s.St.UserByID(p.UserID)
	if err != nil {
		return nil, err
	}
	if u == nil {
		return nil, core.Unauthorized("Требуется вход")
	}
	return u, nil
}

func (s *Server) ownAgent(p *core.Principal, id string) (*store.Agent, error) {
	a, err := s.St.AgentByID(id)
	if err != nil {
		return nil, err
	}
	if a == nil || a.UserID != p.UserID {
		return nil, core.NotFound("Агент не найден")
	}
	return a, nil
}

func (s *Server) Handler() http.Handler {
	m := http.NewServeMux()
	m.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) { s.writeJSON(w, 200, map[string]string{"status": "ok"}) })
	s.authRoutes(m)
	s.apiRoutes(m)
	s.wsRoutes(m)
	return recoverer(m)
}

func recoverer(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if v := recover(); v != nil {
				log.Printf("panic: %v", v)
				http.Error(w, `{"error":"internal"}`, 500)
			}
		}()
		next.ServeHTTP(w, r)
	})
}
