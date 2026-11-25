package core

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"time"
)

type Mailer interface {
	Send(to, subject, text string) error
}

// Brevo отправляет транзакционные письма. Без ключа письма пишутся в лог (режим разработки).
type Brevo struct{ Key, From, FromName string }

func (b Brevo) Send(to, subject, text string) error {
	if b.Key == "" {
		log.Printf("MAIL (Brevo не настроен) to=%s subject=%s\n%s", to, subject, text)
		return nil
	}
	body, _ := json.Marshal(map[string]any{
		"sender":      map[string]string{"name": b.FromName, "email": b.From},
		"to":          []map[string]string{{"email": to}},
		"subject":     subject,
		"textContent": text,
	})
	req, _ := http.NewRequest("POST", "https://api.brevo.com/v3/smtp/email", bytes.NewReader(body))
	req.Header.Set("api-key", b.Key)
	req.Header.Set("content-type", "application/json")
	resp, err := (&http.Client{Timeout: 15 * time.Second}).Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode > 299 {
		log.Printf("Brevo error %d", resp.StatusCode)
		return fmt.Errorf("не удалось отправить письмо")
	}
	return nil
}
