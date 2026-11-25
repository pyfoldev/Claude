// Package core: бизнес-логика (авторизация, сообщения, агенты, инструменты, подтверждения, планировщик).
package core

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"math/big"
	"net/http"
	"sync"
	"time"
)

// APIError — ошибка с HTTP-статусом и кодом для клиента.
type APIError struct {
	Status  int
	Code    string
	Message string
}

func (e *APIError) Error() string { return e.Message }

func Err(status int, code, msg string) *APIError { return &APIError{status, code, msg} }
func BadRequest(code, msg string) *APIError      { return Err(http.StatusBadRequest, code, msg) }
func Unauthorized(msg string) *APIError          { return Err(http.StatusUnauthorized, "unauthorized", msg) }
func Forbidden(msg string) *APIError             { return Err(http.StatusForbidden, "forbidden", msg) }
func NotFound(msg string) *APIError              { return Err(http.StatusNotFound, "not_found", msg) }
func TooMany() *APIError {
	return Err(http.StatusTooManyRequests, "rate_limited", "Слишком много попыток, попробуйте позже")
}

func Sha256Hex(s string) string {
	h := sha256.Sum256([]byte(s))
	return hex.EncodeToString(h[:])
}

func RandomToken(n int) string {
	b := make([]byte, n)
	_, _ = rand.Read(b)
	return base64.RawURLEncoding.EncodeToString(b)
}

func RandomCode() string {
	n, _ := rand.Int(rand.Reader, big.NewInt(1_000_000))
	return fmt.Sprintf("%06d", n.Int64())
}

// SecretBox шифрует секреты (ключи провайдеров) мастер-ключом: AES-256-GCM.
type SecretBox struct{ aead cipher.AEAD }

func NewSecretBox(master string) *SecretBox {
	k := sha256.Sum256([]byte(master))
	b, _ := aes.NewCipher(k[:])
	g, _ := cipher.NewGCM(b)
	return &SecretBox{g}
}

func (s *SecretBox) Seal(plain string) string {
	nonce := make([]byte, s.aead.NonceSize())
	_, _ = rand.Read(nonce)
	return base64.StdEncoding.EncodeToString(s.aead.Seal(nonce, nonce, []byte(plain), nil))
}

func (s *SecretBox) Open(sealed string) (string, error) {
	raw, err := base64.StdEncoding.DecodeString(sealed)
	if err != nil || len(raw) < s.aead.NonceSize() {
		return "", errors.New("повреждённый секрет")
	}
	n := s.aead.NonceSize()
	out, err := s.aead.Open(nil, raw[:n], raw[n:], nil)
	return string(out), err
}

// RateLimiter: не более max событий за window на ключ.
type RateLimiter struct {
	mu   sync.Mutex
	hits map[string][]time.Time
}

func NewRateLimiter() *RateLimiter { return &RateLimiter{hits: map[string][]time.Time{}} }

func (r *RateLimiter) Check(key string, max int, window time.Duration) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	now := time.Now()
	q := r.hits[key][:0]
	for _, t := range r.hits[key] {
		if now.Sub(t) < window {
			q = append(q, t)
		}
	}
	if len(q) >= max {
		r.hits[key] = q
		return TooMany()
	}
	r.hits[key] = append(q, now)
	return nil
}

func (r *RateLimiter) Reset() { r.mu.Lock(); r.hits = map[string][]time.Time{}; r.mu.Unlock() }
