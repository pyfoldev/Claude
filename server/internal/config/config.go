// Package config читает настройки сервера из переменных окружения.
package config

import (
	"crypto/rand"
	"encoding/base64"
	"log"
	"os"
	"strings"
)

type Config struct {
	Port             string
	DBURL            string // postgres://... или sqlite-файл: file:data/staika.db
	JWTSecret        string
	MasterKey        string
	OwnerEmail       string
	RegistrationOpen bool
	GoogleClientIDs  []string
	BrevoAPIKey      string
	MailFrom         string
	MailFromName     string
	WorkspacesDir    string
	AnthropicKey     string
	OpenAIKey        string
	GoogleKey        string
	RiverKey         string
	DeepgramKey      string
	SandboxImage     string
	VoiceSpeakJSON   string
}

func env(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func randomSecret() string {
	b := make([]byte, 48)
	_, _ = rand.Read(b)
	return base64.RawURLEncoding.EncodeToString(b)
}

func Load() Config {
	c := Config{
		Port:             env("PORT", "8080"),
		DBURL:            env("STAIKA_DB_URL", "file:data/staika.db"),
		JWTSecret:        os.Getenv("STAIKA_JWT_SECRET"),
		MasterKey:        os.Getenv("STAIKA_MASTER_KEY"),
		OwnerEmail:       strings.ToLower(os.Getenv("STAIKA_OWNER_EMAIL")),
		RegistrationOpen: env("STAIKA_REGISTRATION_OPEN", "true") != "false",
		BrevoAPIKey:      os.Getenv("BREVO_API_KEY"),
		MailFrom:         env("STAIKA_MAIL_FROM", "no-reply@localhost"),
		MailFromName:     env("STAIKA_MAIL_FROM_NAME", "Стайка"),
		WorkspacesDir:    env("STAIKA_WORKSPACES_DIR", "data/workspaces"),
		AnthropicKey:     os.Getenv("ANTHROPIC_API_KEY"),
		OpenAIKey:        os.Getenv("OPENAI_API_KEY"),
		GoogleKey:        os.Getenv("GOOGLE_API_KEY"),
		RiverKey:         os.Getenv("RIVER_API_KEY"),
		DeepgramKey:      os.Getenv("DEEPGRAM_API_KEY"),
		SandboxImage:     os.Getenv("STAIKA_SANDBOX_IMAGE"),
		VoiceSpeakJSON:   os.Getenv("STAIKA_VOICE_SPEAK_JSON"),
	}
	for _, id := range strings.Split(os.Getenv("STAIKA_GOOGLE_CLIENT_IDS"), ",") {
		if id = strings.TrimSpace(id); id != "" {
			c.GoogleClientIDs = append(c.GoogleClientIDs, id)
		}
	}
	if c.JWTSecret == "" {
		log.Println("WARN: STAIKA_JWT_SECRET не задан, создан временный ключ: сессии сбросятся при перезапуске")
		c.JWTSecret = randomSecret()
	}
	if len(c.JWTSecret) < 32 {
		log.Fatal("STAIKA_JWT_SECRET должен быть не короче 32 символов")
	}
	if c.MasterKey == "" {
		log.Println("WARN: STAIKA_MASTER_KEY не задан: ключи провайдеров не расшифруются после перезапуска")
		c.MasterKey = randomSecret()
	}
	return c
}

// TrustProxy: доверять заголовку X-Forwarded-For (только за своим reverse proxy).
func TrustProxy() bool { return os.Getenv("STAIKA_TRUST_PROXY") == "true" }
