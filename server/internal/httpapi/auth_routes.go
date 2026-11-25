package httpapi

import (
	"net/http"

	"staika/server/internal/core"
)

type credentials struct {
	Email        string `json:"email"`
	Password     string `json:"password"`
	Name         string `json:"name"`
	Device       string `json:"device"`
	Code         string `json:"code"`
	NewPassword  string `json:"newPassword"`
	IDToken      string `json:"idToken"`
	RefreshToken string `json:"refreshToken"`
}

func (s *Server) authRoutes(m *http.ServeMux) {
	// tok оборачивает операцию, возвращающую пару токенов
	tok := func(f func(c credentials, r *http.Request) (*core.TokenPair, error)) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			var c credentials
			if !s.decode(w, r, &c) {
				return
			}
			t, err := f(c, r)
			if err != nil {
				s.fail(w, err)
				return
			}
			s.writeJSON(w, 200, t)
		}
	}
	ok := func(f func(c credentials) error, key string) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			var c credentials
			if !s.decode(w, r, &c) {
				return
			}
			if err := f(c); err != nil {
				s.fail(w, err)
				return
			}
			s.writeJSON(w, 200, map[string]bool{key: true})
		}
	}
	m.HandleFunc("POST /api/auth/register", tok(func(c credentials, r *http.Request) (*core.TokenPair, error) {
		return s.Auth.Register(c.Email, c.Password, c.Name, s.ip(r), c.Device)
	}))
	m.HandleFunc("POST /api/auth/login", tok(func(c credentials, r *http.Request) (*core.TokenPair, error) {
		return s.Auth.Login(c.Email, c.Password, s.ip(r), c.Device)
	}))
	m.HandleFunc("POST /api/auth/code/verify", tok(func(c credentials, r *http.Request) (*core.TokenPair, error) {
		return s.Auth.LoginWithCode(c.Email, c.Code, s.ip(r), c.Device)
	}))
	m.HandleFunc("POST /api/auth/google", tok(func(c credentials, r *http.Request) (*core.TokenPair, error) {
		return s.Auth.LoginGoogle(c.IDToken, s.ip(r), c.Device)
	}))
	m.HandleFunc("POST /api/auth/refresh", tok(func(c credentials, r *http.Request) (*core.TokenPair, error) {
		return s.Auth.Refresh(c.RefreshToken, c.Device)
	}))
	m.HandleFunc("POST /api/auth/code/request", ok(func(c credentials) error { return s.Auth.SendCode(c.Email, "login") }, "sent"))
	m.HandleFunc("POST /api/auth/password/forgot", ok(func(c credentials) error { return s.Auth.SendCode(c.Email, "reset") }, "sent"))
	m.HandleFunc("POST /api/auth/password/reset", ok(func(c credentials) error {
		return s.Auth.ResetPassword(c.Email, c.Code, c.NewPassword)
	}, "ok"))
	m.HandleFunc("POST /api/auth/logout", ok(func(c credentials) error { s.Auth.Logout(c.RefreshToken); return nil }, "ok"))

	m.HandleFunc("POST /api/auth/verify-email", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		var c credentials
		if !s.decode(w, r, &c) {
			return
		}
		if err := s.Auth.VerifyEmail(p.UserID, c.Code); err != nil {
			s.fail(w, err)
			return
		}
		s.writeJSON(w, 200, map[string]bool{"ok": true})
	}))
	m.HandleFunc("POST /api/auth/verify-email/resend", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		u, err := s.user(p)
		if err == nil {
			err = s.Auth.SendCode(u.Email, "verify")
		}
		if err != nil {
			s.fail(w, err)
			return
		}
		s.writeJSON(w, 200, map[string]bool{"sent": true})
	}))
	m.HandleFunc("POST /api/auth/logout-all", s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		s.Auth.LogoutAll(p.UserID)
		s.writeJSON(w, 200, map[string]bool{"ok": true})
	}))
	me := s.secure(func(w http.ResponseWriter, r *http.Request, p *core.Principal) {
		u, err := s.user(p)
		if err != nil {
			s.fail(w, err)
			return
		}
		s.writeJSON(w, 200, core.DTO(u))
	})
	m.HandleFunc("GET /api/auth/me", me)
	m.HandleFunc("GET /api/profile", me)
}
