package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"staika/server/internal/config"
	"staika/server/internal/core"
	"staika/server/internal/httpapi"
	"staika/server/internal/store"
)

func main() {
	cfg := config.Load()
	if cfg.DBURL[:5] == "file:" {
		_ = os.MkdirAll("data", 0o750)
	}
	db, err := store.Open(cfg.DBURL)
	if err != nil {
		log.Fatalf("БД: %v", err)
	}
	st := store.New(db)
	box := core.NewSecretBox(cfg.MasterKey)
	limiter := core.NewRateLimiter()
	router := core.NewRouter(st, box, map[string]string{
		"anthropic": cfg.AnthropicKey, "openai": cfg.OpenAIKey, "google": cfg.GoogleKey, "river": cfg.RiverKey, "deepgram": cfg.DeepgramKey,
	})
	hub := core.NewHub()
	app := core.NewApp(st, hub, router, core.Settings{WorkspacesDir: cfg.WorkspacesDir, SandboxImage: cfg.SandboxImage})
	app.RecoverRuns()
	auth := &core.Auth{
		St: st, Limiter: limiter,
		Cfg:    core.AuthConfig{JWTSecret: []byte(cfg.JWTSecret), OwnerEmail: cfg.OwnerEmail, RegistrationOpen: cfg.RegistrationOpen},
		Mail:   core.Brevo{Key: cfg.BrevoAPIKey, From: cfg.MailFrom, FromName: cfg.MailFromName},
		Google: &core.RemoteGoogle{ClientIDs: cfg.GoogleClientIDs},
	}
	srv := &httpapi.Server{App: app, Auth: auth, St: st, Router: router, Box: box, Limiter: limiter, Cfg: cfg, TrustProxy: config.TrustProxy()}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	app.StartScheduler(ctx)

	hs := &http.Server{Addr: ":" + cfg.Port, Handler: srv.Handler(), ReadHeaderTimeout: 10 * time.Second}
	go func() {
		<-ctx.Done()
		sc, c := context.WithTimeout(context.Background(), 10*time.Second)
		defer c()
		_ = hs.Shutdown(sc)
	}()
	log.Printf("Стайка: сервер запущен на :%s", cfg.Port)
	if err := hs.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatal(err)
	}
}
