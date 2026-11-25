package core

import (
	"encoding/json"
	"sync"
)

// Hub рассылает события клиентам (WebSocket). Отправка идёт через канал, медленный клиент не блокирует остальных.
type Client struct {
	UserID string
	Send   chan []byte
}

type Hub struct {
	mu      sync.RWMutex
	clients map[string]map[*Client]struct{}
}

func NewHub() *Hub { return &Hub{clients: map[string]map[*Client]struct{}{}} }

func (h *Hub) Add(c *Client) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if h.clients[c.UserID] == nil {
		h.clients[c.UserID] = map[*Client]struct{}{}
	}
	h.clients[c.UserID][c] = struct{}{}
}

func (h *Hub) Remove(c *Client) {
	h.mu.Lock()
	defer h.mu.Unlock()
	delete(h.clients[c.UserID], c)
}

func (h *Hub) Online(userID string) bool {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.clients[userID]) > 0
}

// Publish: события message.created, message.updated, agent.updated, approval.created, approval.updated.
func (h *Hub) Publish(userID, typ string, data any) {
	b, err := json.Marshal(map[string]any{"type": typ, "data": data})
	if err != nil {
		return
	}
	h.mu.RLock()
	defer h.mu.RUnlock()
	for c := range h.clients[userID] {
		select {
		case c.Send <- b:
		default: // клиент не успевает: пропускаем, он догрузит историю по REST
		}
	}
}
