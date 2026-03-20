# 📋 Шпаргалка: Установка GitHub MCP Server (Локально)

> Источник: https://github.com/github/github-mcp-server

---

## ✅ Шаг 0 — Что нужно заранее

| Требование | Где взять |
|---|---|
| 🐳 Docker | https://www.docker.com/ |
| 🔑 GitHub PAT (токен) | https://github.com/settings/personal-access-tokens/new |
| 🖥️ VS Code (опционально) | https://code.visualstudio.com/ |

### Минимальные права для PAT (токена):
- `repo` — операции с репозиториями
- `read:org` — доступ к организациям
- `notifications` — уведомления (если нужно)

### Безопасное хранение токена:
```bash
# Сохрани в переменную среды (Linux/Mac)
export GITHUB_PAT=твой_токен_здесь

# Или создай .env файл
echo "GITHUB_PAT=твой_токен_здесь" > .env
echo ".env" >> .gitignore  # ← ВАЖНО! не коммитить токен
```

---

## 🚀 Способ 1 — VS Code (Один клик)

1. Открой ссылку → [Установить в VS Code](https://insiders.vscode.dev/redirect/mcp/install?name=github&inputs=%5B%7B%22id%22%3A%22github_token%22%2C%22type%22%3A%22promptString%22%2C%22description%22%3A%22GitHub%20Personal%20Access%20Token%22%2C%22password%22%3Atrue%7D%5D&config=%7B%22command%22%3A%22docker%22%2C%22args%22%3A%5B%22run%22%2C%22-i%22%2C%22--rm%22%2C%22-e%22%2C%22GITHUB_PERSONAL_ACCESS_TOKEN%22%2C%22ghcr.io%2Fgithub%2Fgithub-mcp-server%22%5D%2C%22env%22%3A%7B%22GITHUB_PERSONAL_ACCESS_TOKEN%22%3A%22%24%7Binput%3Agithub_token%7D%22%7D%7D)
2. Введи PAT токен когда спросит
3. Переключись в **Agent mode** в Copilot Chat
4. Готово! ✅

---

## 🐳 Способ 2 — Docker вручную (рекомендуется)

### Просто запустить:
```bash
docker run -i --rm \
  -e GITHUB_PERSONAL_ACCESS_TOKEN=твой_токен \
  ghcr.io/github/github-mcp-server
```

### Если Docker не может скачать образ:
```bash
docker logout ghcr.io
docker pull ghcr.io/github/github-mcp-server
```

---

## ⚙️ Способ 3 — Настройка в VS Code вручную

### Открой настройки:
`Ctrl+Shift+P` → **"Preferences: Open User Settings (JSON)"**

### Добавь блок (с запросом токена при запуске):
```json
{
  "mcp": {
    "inputs": [
      {
        "type": "promptString",
        "id": "github_token",
        "description": "GitHub Personal Access Token",
        "password": true
      }
    ],
    "servers": {
      "github": {
        "command": "docker",
        "args": [
          "run", "-i", "--rm", "-e",
          "GITHUB_PERSONAL_ACCESS_TOKEN",
          "ghcr.io/github/github-mcp-server"
        ],
        "env": {
          "GITHUB_PERSONAL_ACCESS_TOKEN": "${input:github_token}"
        }
      }
    }
  }
}
```

### Или добавь файл `.vscode/mcp.json` в проект:
```json
{
  "inputs": [
    {
      "type": "promptString",
      "id": "github_token",
      "description": "GitHub Personal Access Token",
      "password": true
    }
  ],
  "servers": {
    "github": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm", "-e",
        "GITHUB_PERSONAL_ACCESS_TOKEN",
        "ghcr.io/github/github-mcp-server"
      ],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${input:github_token}"
      }
    }
  }
}
```

---

## 🛠️ Способ 4 — Сборка из исходников (без Docker)

### Требования: Go установлен

```bash
# Клонируй репозиторий
git clone https://github.com/github/github-mcp-server
cd github-mcp-server

# Собери бинарник
go build -o github-mcp-server ./cmd/github-mcp-server
```

### Настрой в mcp settings:
```json
{
  "mcp": {
    "servers": {
      "github": {
        "command": "/путь/до/github-mcp-server",
        "args": ["stdio"],
        "env": {
          "GITHUB_PERSONAL_ACCESS_TOKEN": "твой_токен"
        }
      }
    }
  }
}
```

### Или через go run (без сборки):
```json
{
  "github": {
    "command": "go",
    "args": [
      "run",
      "github.com/github/github-mcp-server/cmd/github-mcp-server@latest",
      "stdio"
    ],
    "env": {
      "GITHUB_PERSONAL_ACCESS_TOKEN": "твой_токен"
    }
  }
}
```

---

## 🔧 Полезные переменные среды (Docker)

```bash
# Включить все инструменты
-e GITHUB_TOOLSETS="all"

# Только нужные наборы
-e GITHUB_TOOLSETS="repos,issues,pull_requests,actions"

# Только для чтения (без изменений)
-e GITHUB_READ_ONLY=1

# Режим Insiders (ранний доступ к фичам)
-e GITHUB_INSIDERS=true

# Динамическое обнаружение инструментов (beta)
-e GITHUB_DYNAMIC_TOOLSETS=1
```

### Пример с настройками:
```bash
docker run -i --rm \
  -e GITHUB_PERSONAL_ACCESS_TOKEN=твой_токен \
  -e GITHUB_TOOLSETS="repos,issues,pull_requests,actions" \
  -e GITHUB_READ_ONLY=1 \
  ghcr.io/github/github-mcp-server
```

---

## 📦 Доступные наборы инструментов (Toolsets)

| Toolset | Описание |
|---|---|
| `context` | ⭐ Рекомендуется всегда включать |
| `repos` | Работа с репозиториями |
| `issues` | Issues (задачи) |
| `pull_requests` | Pull Requests |
| `actions` | GitHub Actions / CI-CD |
| `code_security` | Code Scanning |
| `dependabot` | Dependabot alerts |
| `notifications` | Уведомления |
| `discussions` | Discussions |
| `projects` | GitHub Projects |
| `users` | Пользователи |
| `gists` | Gists |
| `orgs` | Организации |
| `labels` | Метки |
| `stargazers` | Звёзды |
| `all` | 🔥 Все инструменты сразу |

### По умолчанию включены:
`context`, `repos`, `issues`, `pull_requests`, `users`

---

## 🔍 Поиск инструментов (отладка)

```bash
# Поиск инструментов по ключевому слову
docker run -it --rm ghcr.io/github/github-mcp-server \
  tool-search "issue" --max-results 5
```

---

## 🌐 GitHub Enterprise Server

```json
"github": {
  "command": "docker",
  "args": [
    "run", "-i", "--rm",
    "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
    "-e", "GITHUB_HOST",
    "ghcr.io/github/github-mcp-server"
  ],
  "env": {
    "GITHUB_PERSONAL_ACCESS_TOKEN": "твой_токен",
    "GITHUB_HOST": "https://твой-домен.ghe.com"
  }
}
```

---

## 📚 Ссылки

| Ресурс | Ссылка |
|---|---|
| Репозиторий | https://github.com/github/github-mcp-server |
| Гайды установки | https://github.com/github/github-mcp-server/tree/main/docs/installation-guides |
| Claude Desktop | docs/installation-guides/install-claude.md |
| Cursor | docs/installation-guides/install-cursor.md |
| Windsurf | docs/installation-guides/install-windsurf.md |
| Copilot CLI | docs/installation-guides/install-copilot-cli.md |

---

> 💡 **Совет**: Начни с Способа 1 (один клик) если используешь VS Code.
> Если что-то не работает — переходи к Способу 2 (Docker вручную).