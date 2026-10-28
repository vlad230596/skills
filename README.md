# Skills

Общие скиллы Claude Code (и других агентов, читающих `SKILL.md`).

| Скилл | Что делает |
|---|---|
| [`ipc-2581`](skills/ipc-2581/SKILL.md) | Файлы IPC-2581 (.cvg/.xml из Altium): разбор, осмотр, рисование геометрии платы; грабли формата |
| [`project-conventions`](skills/project-conventions/SKILL.md) | Единые правила структуры проектов (uv, AGENTS.md, docs/) — проверка и приведение к стандарту |

## Подключение

Каждый скилл — папка `skills/<имя>/` со своим `SKILL.md`. Подключается ссылкой (Windows — junction):

```powershell
New-Item -ItemType Junction -Path "$env:USERPROFILE\.claude\skills\ipc-2581" -Target "<клон>\skills\ipc-2581"
```

Проекты, которым скилл нужен локально (например, импортируют `ipc2581.py`), держат такую же ссылку в своей
`.claude/skills/`.
