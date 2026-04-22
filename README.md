# LP Monitor - Discogs Vinyl Tracker

Self-hosted web app per monitorare Discogs marketplace per vinili nella tua wantlist. Notifiche email/Telegram per nuovi match sotto prezzo target.

## Quick Start

```bash
git clone https://github.com/DFFM-maker/discogs.git lp-monitor
cd lp-monitor
cp .env.example .env
# edita .env con DISCOSG_TOKEN, CLAUDE_API_KEY, SMTP_*
docker compose up -d
```

## Features
- Wishlist con priorità, prezzo max, note
- Scansioni programmate (rate limit compliant)
- Matching con Claude AI
- Risultati filtrati con bulk actions
- Notifiche email/Telegram

## Architecture
docker-compose.yml → FastAPI backend + Postgres + Redis + Worker

text
Frontend statico da prototype → Vite/React

## Configuration
Vedi `.env.example`

## API Docs
Swagger UI su /docs

## License
MIT
