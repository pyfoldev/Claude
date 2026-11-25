// Package store: доступ к БД (SQLite для разработки, PostgreSQL для продакшена).
package store

import (
	"database/sql"
	_ "embed"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	_ "github.com/jackc/pgx/v5/stdlib"
	_ "modernc.org/sqlite"
)

//go:embed migrations_sqlite.sql
var migSQLite string

//go:embed migrations_postgres.sql
var migPostgres string

// DB добавляет к *sql.DB перенумерацию плейсхолдеров (? -> $1 для PostgreSQL).
type DB struct {
	*sql.DB
	PG bool
}

func Open(url string) (*DB, error) {
	var d *DB
	if strings.HasPrefix(url, "postgres://") || strings.HasPrefix(url, "postgresql://") {
		sdb, err := sql.Open("pgx", url)
		if err != nil {
			return nil, err
		}
		sdb.SetMaxOpenConns(20)
		d = &DB{sdb, true}
	} else {
		dsn := url
		sep := "?"
		if strings.Contains(dsn, "?") {
			sep = "&"
		}
		dsn += sep + "_pragma=busy_timeout(10000)&_pragma=journal_mode(WAL)&_pragma=foreign_keys(1)"
		sdb, err := sql.Open("sqlite", dsn)
		if err != nil {
			return nil, err
		}
		sdb.SetMaxOpenConns(1) // SQLite: один писатель; запросы короткие, строки всегда закрываются
		d = &DB{sdb, false}
	}
	if err := d.Ping(); err != nil {
		return nil, err
	}
	mig := migSQLite
	if d.PG {
		mig = migPostgres
	}
	for _, stmt := range strings.Split(mig, ";\n") {
		if strings.TrimSpace(stmt) == "" {
			continue
		}
		if _, err := d.DB.Exec(stmt); err != nil {
			return nil, fmt.Errorf("миграция: %w\n%s", err, stmt)
		}
	}
	return d, nil
}

func (d *DB) rb(q string) string {
	if !d.PG {
		return q
	}
	var b strings.Builder
	n := 0
	for _, r := range q {
		if r == '?' {
			n++
			b.WriteString("$" + strconv.Itoa(n))
		} else {
			b.WriteRune(r)
		}
	}
	return b.String()
}

func (d *DB) Exec(q string, a ...any) (sql.Result, error) { return d.DB.Exec(d.rb(q), a...) }
func (d *DB) Query(q string, a ...any) (*sql.Rows, error) { return d.DB.Query(d.rb(q), a...) }
func (d *DB) QueryRow(q string, a ...any) *sql.Row        { return d.DB.QueryRow(d.rb(q), a...) }

func Now() int64 { return time.Now().UnixMilli() }

func b2i(b bool) int {
	if b {
		return 1
	}
	return 0
}

func nf(err error) error {
	if errors.Is(err, sql.ErrNoRows) {
		return nil
	}
	return err
}

// Store — все операции с данными.
type Store struct{ DB *DB }

func New(db *DB) *Store { return &Store{db} }
