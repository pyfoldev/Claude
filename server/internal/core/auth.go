package core

import (
	"crypto/rand"
	"crypto/subtle"
	"encoding/base64"
	"fmt"
	"regexp"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"golang.org/x/crypto/argon2"

	"staika/server/internal/store"
)

type UserDTO struct {
	ID            string `json:"id"`
	Email         string `json:"email"`
	Name          string `json:"name"`
	Role          string `json:"role"`
	EmailVerified bool   `json:"emailVerified"`
}

func DTO(u *store.User) UserDTO { return UserDTO{u.ID, u.Email, u.Name, u.Role, u.EmailVerified} }

type TokenPair struct {
	AccessToken  string  `json:"accessToken"`
	RefreshToken string  `json:"refreshToken"`
	ExpiresIn    int64   `json:"expiresIn"`
	User         UserDTO `json:"user"`
}

type GoogleIdentity struct{ Sub, Email, Name string }

// GoogleVerifier проверяет Google ID-токен (в проде: подпись по JWKS Google).
type GoogleVerifier interface {
	Verify(idToken string) (*GoogleIdentity, error)
}

type AuthConfig struct {
	JWTSecret        []byte
	OwnerEmail       string
	RegistrationOpen bool
}

type Auth struct {
	St      *store.Store
	Cfg     AuthConfig
	Mail    Mailer
	Limiter *RateLimiter
	Google  GoogleVerifier
}

var emailRe = regexp.MustCompile(`^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$`)

const (
	AccessTTL  = 15 * time.Minute
	refreshTTL = 60 * 24 * time.Hour
)

// ---------- пароли: Argon2id ----------

func hashPassword(pw string) string {
	salt := make([]byte, 16)
	_, _ = rand.Read(salt)
	h := argon2.IDKey([]byte(pw), salt, 3, 64*1024, 2, 32)
	return fmt.Sprintf("$argon2id$%s$%s", base64.RawStdEncoding.EncodeToString(salt), base64.RawStdEncoding.EncodeToString(h))
}

func checkPassword(pw, enc string) bool {
	p := strings.Split(enc, "$")
	if len(p) != 4 || p[1] != "argon2id" {
		return false
	}
	salt, e1 := base64.RawStdEncoding.DecodeString(p[2])
	want, e2 := base64.RawStdEncoding.DecodeString(p[3])
	if e1 != nil || e2 != nil {
		return false
	}
	got := argon2.IDKey([]byte(pw), salt, 3, 64*1024, 2, 32)
	return subtle.ConstantTimeCompare(got, want) == 1
}

// ---------- JWT ----------

type Principal struct{ UserID, Role string }

func (a *Auth) IssueAccess(userID, role string) string {
	t := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub": userID, "role": role, "iss": "staika",
		"iat": time.Now().Unix(), "exp": time.Now().Add(AccessTTL).Unix(),
	})
	s, _ := t.SignedString(a.Cfg.JWTSecret)
	return s
}

func (a *Auth) ParseAccess(token string) (*Principal, error) {
	t, err := jwt.Parse(token, func(t *jwt.Token) (any, error) { return a.Cfg.JWTSecret, nil },
		jwt.WithValidMethods([]string{"HS256"}), jwt.WithExpirationRequired())
	if err != nil || !t.Valid {
		return nil, Unauthorized("Недействительный или просроченный токен")
	}
	c := t.Claims.(jwt.MapClaims)
	sub, _ := c["sub"].(string)
	role, _ := c["role"].(string)
	if sub == "" {
		return nil, Unauthorized("Недействительный токен")
	}
	return &Principal{sub, role}, nil
}

// ---------- внутренние помощники ----------

func (a *Auth) normEmail(e string) (string, error) {
	x := strings.ToLower(strings.TrimSpace(e))
	if !emailRe.MatchString(x) {
		return "", BadRequest("bad_email", "Некорректная почта")
	}
	return x, nil
}

func (a *Auth) roleForNew(email string) string {
	n, _ := a.St.CountUsers()
	if n == 0 || (a.Cfg.OwnerEmail != "" && a.Cfg.OwnerEmail == email) {
		return "owner"
	}
	return "member"
}

func (a *Auth) ensureOpen(email string) error {
	if a.Cfg.RegistrationOpen {
		return nil
	}
	u, _ := a.St.UserByEmail(email)
	n, _ := a.St.CountUsers()
	if u == nil && a.Cfg.OwnerEmail != email && n > 0 {
		return Forbidden("Регистрация закрыта")
	}
	return nil
}

func (a *Auth) issue(u *store.User, device string) (*TokenPair, error) {
	refresh := RandomToken(40)
	if err := a.St.AddRefresh(u.ID, Sha256Hex(refresh), device, time.Now().Add(refreshTTL).UnixMilli()); err != nil {
		return nil, err
	}
	return &TokenPair{a.IssueAccess(u.ID, u.Role), refresh, int64(AccessTTL.Seconds()), DTO(u)}, nil
}

// ---------- публичные операции ----------

func (a *Auth) Register(emailRaw, password, name, ip, device string) (*TokenPair, error) {
	if err := a.Limiter.Check("reg:"+ip, 10, time.Hour); err != nil {
		return nil, err
	}
	email, err := a.normEmail(emailRaw)
	if err != nil {
		return nil, err
	}
	if len([]rune(password)) < 8 {
		return nil, BadRequest("weak_password", "Пароль не короче 8 символов")
	}
	if err := a.ensureOpen(email); err != nil {
		return nil, err
	}
	if u, _ := a.St.UserByEmail(email); u != nil {
		return nil, BadRequest("email_taken", "Эта почта уже зарегистрирована")
	}
	name = strings.TrimSpace(name)
	if name == "" {
		name = strings.Split(email, "@")[0]
	}
	if r := []rune(name); len(r) > 80 {
		name = string(r[:80])
	}
	u, err := a.St.CreateUser(email, name, hashPassword(password), "", a.roleForNew(email), false)
	if err != nil {
		return nil, err
	}
	_ = a.SendCode(email, "verify")
	a.St.Audit(u.ID, "", "register", email)
	return a.issue(u, device)
}

func (a *Auth) Login(emailRaw, password, ip, device string) (*TokenPair, error) {
	email, err := a.normEmail(emailRaw)
	if err != nil {
		return nil, err
	}
	if err := a.Limiter.Check("login:"+ip, 30, 10*time.Minute); err != nil {
		return nil, err
	}
	if err := a.Limiter.Check("login:"+email, 8, 10*time.Minute); err != nil {
		return nil, err
	}
	u, _ := a.St.UserByEmail(email)
	// одинаковое сообщение: не раскрываем, существует ли аккаунт
	if u == nil || u.PasswordHash == "" || !checkPassword(password, u.PasswordHash) {
		return nil, Unauthorized("Неверная почта или пароль")
	}
	return a.issue(u, device)
}

func (a *Auth) SendCode(emailRaw, purpose string) error {
	email, err := a.normEmail(emailRaw)
	if err != nil {
		return err
	}
	if err := a.Limiter.Check("code:"+email, 5, 15*time.Minute); err != nil {
		return err
	}
	if purpose == "reset" {
		if u, _ := a.St.UserByEmail(email); u == nil {
			return nil // не раскрываем существование аккаунта
		}
	}
	if purpose == "login" {
		if err := a.ensureOpen(email); err != nil {
			return err
		}
	}
	code := RandomCode()
	if err := a.St.AddCode(email, purpose, Sha256Hex(email+":"+purpose+":"+code), time.Now().Add(10*time.Minute).UnixMilli()); err != nil {
		return err
	}
	subj, text := "Подтвердите почту в Стайке", "Код подтверждения почты: "+code+"\nОн действует 10 минут."
	switch purpose {
	case "login":
		subj, text = "Код для входа в Стайку", "Ваш код входа: "+code+"\nОн действует 10 минут. Если вы не запрашивали код, просто проигнорируйте письмо."
	case "reset":
		subj, text = "Сброс пароля в Стайке", "Код для сброса пароля: "+code+"\nОн действует 10 минут. Если вы не запрашивали сброс, ничего не делайте."
	}
	return a.Mail.Send(email, subj, text)
}

// consumeCode проверяет и гасит код. После 5 неверных попыток код блокируется.
func (a *Auth) consumeCode(email, purpose, code string) error {
	c, _ := a.St.LatestCode(email, purpose)
	if c == nil {
		return BadRequest("bad_code", "Код не найден, запросите новый")
	}
	if c.Expires < time.Now().UnixMilli() {
		return BadRequest("code_expired", "Код истёк, запросите новый")
	}
	if c.Attempts >= 5 {
		return BadRequest("code_locked", "Слишком много попыток, запросите новый код")
	}
	if subtle.ConstantTimeCompare([]byte(c.Hash), []byte(Sha256Hex(email+":"+purpose+":"+strings.TrimSpace(code)))) != 1 {
		_ = a.St.CodeAttempt(c.ID)
		return BadRequest("bad_code", "Неверный код")
	}
	return a.St.CodeUsed(c.ID)
}

func (a *Auth) LoginWithCode(emailRaw, code, ip, device string) (*TokenPair, error) {
	email, err := a.normEmail(emailRaw)
	if err != nil {
		return nil, err
	}
	if err := a.Limiter.Check("codelogin:"+ip, 30, 10*time.Minute); err != nil {
		return nil, err
	}
	if err := a.consumeCode(email, "login", code); err != nil {
		return nil, err
	}
	u, _ := a.St.UserByEmail(email)
	if u == nil {
		if u, err = a.St.CreateUser(email, strings.Split(email, "@")[0], "", "", a.roleForNew(email), true); err != nil {
			return nil, err
		}
	} else if !u.EmailVerified {
		_ = a.St.SetVerified(u.ID)
		u.EmailVerified = true
	}
	return a.issue(u, device)
}

func (a *Auth) VerifyEmail(userID, code string) error {
	u, _ := a.St.UserByID(userID)
	if u == nil {
		return Unauthorized("Требуется вход")
	}
	if err := a.consumeCode(u.Email, "verify", code); err != nil {
		return err
	}
	return a.St.SetVerified(u.ID)
}

func (a *Auth) ResetPassword(emailRaw, code, newPassword string) error {
	email, err := a.normEmail(emailRaw)
	if err != nil {
		return err
	}
	if err := a.Limiter.Check("reset:"+email, 10, 15*time.Minute); err != nil {
		return err
	}
	if len([]rune(newPassword)) < 8 {
		return BadRequest("weak_password", "Пароль не короче 8 символов")
	}
	if err := a.consumeCode(email, "reset", code); err != nil {
		return err
	}
	u, _ := a.St.UserByEmail(email)
	if u == nil {
		return BadRequest("bad_code", "Код не найден, запросите новый")
	}
	_ = a.St.SetPassword(u.ID, hashPassword(newPassword))
	_ = a.St.SetVerified(u.ID)
	_ = a.St.RevokeAllRefresh(u.ID)
	a.St.Audit(u.ID, "", "password_reset", email)
	return nil
}

func (a *Auth) LoginGoogle(idToken, ip, device string) (*TokenPair, error) {
	if err := a.Limiter.Check("google:"+ip, 30, 10*time.Minute); err != nil {
		return nil, err
	}
	g, err := a.Google.Verify(idToken)
	if err != nil {
		return nil, err
	}
	email := strings.ToLower(g.Email)
	u, _ := a.St.UserByGoogle(g.Sub)
	if u == nil {
		if u, _ = a.St.UserByEmail(email); u != nil {
			_ = a.St.SetGoogle(u.ID, g.Sub)
		} else {
			if err := a.ensureOpen(email); err != nil {
				return nil, err
			}
			name := g.Name
			if r := []rune(name); len(r) > 80 {
				name = string(r[:80])
			}
			if u, err = a.St.CreateUser(email, name, "", g.Sub, a.roleForNew(email), true); err != nil {
				return nil, err
			}
		}
	}
	u, _ = a.St.UserByID(u.ID)
	return a.issue(u, device)
}

func (a *Auth) Refresh(token, device string) (*TokenPair, error) {
	r, _ := a.St.RefreshByHash(Sha256Hex(token))
	if r == nil {
		return nil, Unauthorized("Сессия недействительна")
	}
	if r.Revoked || r.Expires < time.Now().UnixMilli() {
		// повторное использование отозванного токена считаем утечкой и закрываем все сессии
		if r.Revoked {
			_ = a.St.RevokeAllRefresh(r.UserID)
		}
		return nil, Unauthorized("Сессия истекла, войдите снова")
	}
	_ = a.St.RevokeRefresh(r.ID)
	u, _ := a.St.UserByID(r.UserID)
	if u == nil {
		return nil, Unauthorized("Требуется вход")
	}
	return a.issue(u, device)
}

func (a *Auth) Logout(token string)     { _ = a.St.RevokeRefreshByHash(Sha256Hex(token)) }
func (a *Auth) LogoutAll(userID string) { _ = a.St.RevokeAllRefresh(userID) }
