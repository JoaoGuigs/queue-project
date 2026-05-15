# Deploy no servidor Linux (ezipbx / Apache)

Guia do que foi feito para publicar o **Queue Activity Report** no servidor PBX (`200.152.183.152`), com backend FastAPI na porta **8001** (systemd) e frontend + proxy `/api` no Apache na porta **8081**.

---

## Estrutura do projeto

```
queue-project-github/
├── backend/
│   ├── app/                 # FastAPI
│   ├── requirements.txt
│   ├── .env.example
│   └── .env                 # só no servidor (não vai pro Git)
├── frontend/
│   ├── index.html
│   ├── css/app.css
│   └── js/app.js
└── tests/
```

No servidor:

```
/var/www/proj_queue/
├── backend/
└── frontend/
```

---

## Arquitetura em produção

```
Navegador
    │
    ▼
Apache :8081  ── GET /              → /var/www/proj_queue/frontend/
    │
    └── POST/GET /api/*  ──proxy──►  uvicorn :8001 (127.0.0.1)
                                          │
                                          ▼
                                    MySQL local (PBX)
```

- **Frontend:** `http://200.152.183.152:8081/`
- **API (via proxy):** `http://200.152.183.152:8081/api/...`
- **API direta (só no servidor):** `http://127.0.0.1:8001/...`

---

## 1. Preparar o código (PC)

O backend ficou em `backend/` (antes `app/` estava na raiz). Testes locais:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Commit e push para o GitHub com a estrutura `backend/` + `frontend/`.

---

## 2. Publicar no servidor (git clone)

```bash
cd /var/www
sudo rm -rf proj_queue          # só se a pasta estiver vazia ou for recriar
sudo git clone https://github.com/SEU_USUARIO/queue-project-github.git proj_queue
```

Conferir:

```bash
ls /var/www/proj_queue/backend/app
ls /var/www/proj_queue/frontend/index.html
```

---

## 3. Backend: venv e `.env`

```bash
cd /var/www/proj_queue/backend
sudo python3 -m venv .venv
sudo .venv/bin/pip install --upgrade pip
sudo .venv/bin/pip install -r requirements.txt
sudo nano .env
```

Conteúdo do `.env` (ajustar com credenciais reais do MySQL do PBX):

```env
DATABASE_HOST=127.0.0.1
DATABASE_PORT=3306
DATABASE_USER=root
DATABASE_PASSWORD=SUA_SENHA
DATABASE_NAME=pbx
API_KEY=chave-longa-e-secreta
```

Permissões:

```bash
sudo chown -R www-data:www-data /var/www/proj_queue
sudo chmod 640 /var/www/proj_queue/backend/.env
```

Teste rápido:

```bash
sudo .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
# outro terminal:
curl -s http://127.0.0.1:8001/health
# → {"status":"ok"}
# Ctrl+C e seguir para o systemd
```

---

## 4. Systemd (API sempre ativa na 8001)

Arquivo `/etc/systemd/system/proj_queue.service`:

```ini
[Unit]
Description=Queue Activity Report API
After=network.target mysql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/proj_queue/backend
EnvironmentFile=/var/www/proj_queue/backend/.env
ExecStart=/var/www/proj_queue/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Ativar:

```bash
sudo systemctl daemon-reload
sudo systemctl enable proj_queue
sudo systemctl start proj_queue
sudo systemctl status proj_queue
curl -s http://127.0.0.1:8001/health
```

Comandos úteis:

```bash
sudo systemctl restart proj_queue
journalctl -u proj_queue -f
```

---

## 5. Apache: porta 8081 e site `proj_queue`

### 5.1 Liberar a porta 8081

Em `/etc/apache2/ports.conf`, adicionar (junto aos outros `Listen`):

```apache
Listen 8081
```

### 5.2 Virtual host

Arquivo `/etc/apache2/sites-available/proj_queue.conf`:

```apache
<VirtualHost *:8081>
    ServerAdmin redbox@ezvoice.com.br

    ProxyPreserveHost On
    ProxyPass        /api/ http://127.0.0.1:8001/
    ProxyPassReverse /api/ http://127.0.0.1:8001/

    DocumentRoot /var/www/proj_queue/frontend

    <Directory /var/www/proj_queue/frontend>
        Options +FollowSymLinks
        AllowOverride None
        Require all granted
        DirectoryIndex index.html
    </Directory>

    ErrorLog  /var/log/apache2/proj_queue-error.log
    CustomLog /var/log/apache2/proj_queue-access.log combined
    LogLevel warn
</VirtualHost>
```

**Importante:** `ProxyPass /api/` e `http://127.0.0.1:8001/` **com barra no final** — assim `/api/health` vira `/health` no FastAPI e `/api/reports/queue-activity` vira `/reports/queue-activity`.

### 5.3 Ativar módulos e site

```bash
sudo a2enmod proxy proxy_http headers
sudo a2ensite proj_queue.conf
sudo apache2ctl configtest
sudo systemctl restart apache2
```

### 5.4 Testes

```bash
curl -s http://127.0.0.1:8081/api/health
# → {"status":"ok"}

curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8081/api/reports/queue-activity \
  -H "Content-Type: application/json" \
  -H "X-API-Key: SUA_API_KEY" \
  -d '{"period_type":"weekly","year":2026,"week":20}'
# → 200
```

---

## 6. Usar o dashboard no navegador

1. Abrir: **http://200.152.183.152:8081/**
2. Painel **Autenticação:** informar a mesma `API_KEY` do `backend/.env` e **Salvar na sessão**.
3. Gerar o relatório (a URL da API é definida automaticamente como `origin + /api`).

A requisição enviada pelo front:

`POST http://200.152.183.152:8081/api/reports/queue-activity`

---

## 7. Atualizar o projeto no servidor

```bash
cd /var/www/proj_queue
sudo git pull
sudo systemctl restart proj_queue
```

Se mudar só o frontend, basta `git pull` (Apache serve os arquivos estáticos direto).

---

## Checklist final

| Item | Como verificar |
|------|----------------|
| Backend | `curl http://127.0.0.1:8001/health` → `ok` |
| Proxy Apache | `curl http://127.0.0.1:8081/api/health` → `ok` |
| Relatório | POST `/api/reports/queue-activity` → HTTP 200 |
| Front | `http://IP:8081/` abre o dashboard |
| Systemd | `systemctl status proj_queue` → `active (running)` |

---

## Referência rápida de caminhos

| O quê | Caminho |
|-------|---------|
| Código | `/var/www/proj_queue/` |
| `.env` | `/var/www/proj_queue/backend/.env` |
| Service systemd | `/etc/systemd/system/proj_queue.service` |
| Site Apache | `/etc/apache2/sites-available/proj_queue.conf` |
| Logs Apache | `/var/log/apache2/proj_queue-*.log` |
| Logs API | `journalctl -u proj_queue` |

---

## Desenvolvimento local (Windows)

```powershell
cd backend
..\.venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Front + API no mesmo processo: `http://localhost:8000/` (modo dev com `StaticFiles` no `main.py`).

Testes na raiz do repo:

```bash
pytest -q
```
