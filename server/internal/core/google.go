package core

import (
	"crypto/rsa"
	"encoding/base64"
	"encoding/json"
	"math/big"
	"net/http"
	"sync"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

// RemoteGoogle проверяет подпись ID-токена по ключам Google (JWKS), издателя, аудиторию и срок.
type RemoteGoogle struct {
	ClientIDs []string
	mu        sync.Mutex
	keys      map[string]*rsa.PublicKey
	fetched   time.Time
}

func (g *RemoteGoogle) key(kid string) (*rsa.PublicKey, error) {
	g.mu.Lock()
	defer g.mu.Unlock()
	if k, ok := g.keys[kid]; ok && time.Since(g.fetched) < 6*time.Hour {
		return k, nil
	}
	resp, err := (&http.Client{Timeout: 10 * time.Second}).Get("https://www.googleapis.com/oauth2/v3/certs")
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var set struct {
		Keys []struct{ Kid, N, E string } `json:"keys"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&set); err != nil {
		return nil, err
	}
	g.keys = map[string]*rsa.PublicKey{}
	for _, k := range set.Keys {
		n, e1 := base64.RawURLEncoding.DecodeString(k.N)
		e, e2 := base64.RawURLEncoding.DecodeString(k.E)
		if e1 != nil || e2 != nil {
			continue
		}
		g.keys[k.Kid] = &rsa.PublicKey{N: new(big.Int).SetBytes(n), E: int(new(big.Int).SetBytes(e).Int64())}
	}
	g.fetched = time.Now()
	if k, ok := g.keys[kid]; ok {
		return k, nil
	}
	return nil, jwt.ErrTokenUnverifiable
}

func (g *RemoteGoogle) Verify(idToken string) (*GoogleIdentity, error) {
	if len(g.ClientIDs) == 0 {
		return nil, BadRequest("google_disabled", "Вход через Google не настроен на сервере")
	}
	bad := BadRequest("google_invalid", "Не удалось проверить вход через Google")
	claims := jwt.MapClaims{}
	_, err := jwt.ParseWithClaims(idToken, claims, func(t *jwt.Token) (any, error) {
		kid, _ := t.Header["kid"].(string)
		return g.key(kid)
	}, jwt.WithValidMethods([]string{"RS256"}), jwt.WithExpirationRequired())
	if err != nil {
		return nil, bad
	}
	if iss, _ := claims["iss"].(string); iss != "https://accounts.google.com" && iss != "accounts.google.com" {
		return nil, bad
	}
	okAud := false
	aud, _ := claims.GetAudience()
	for _, a := range aud {
		for _, id := range g.ClientIDs {
			if a == id {
				okAud = true
			}
		}
	}
	if !okAud {
		return nil, bad
	}
	if v, _ := claims["email_verified"].(bool); !v {
		return nil, BadRequest("google_unverified", "Почта Google не подтверждена")
	}
	email, _ := claims["email"].(string)
	sub, _ := claims["sub"].(string)
	name, _ := claims["name"].(string)
	if email == "" || sub == "" {
		return nil, bad
	}
	return &GoogleIdentity{sub, email, name}, nil
}
