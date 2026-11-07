# CKRPRO MUSIC (Vercel)

## Deploy
```bash
vercel --prod
```

## Fix applied
- Audio resolve: **Piped → Cobalt → yt-dlp** (multi fallback)
- yt-dlp multi player clients: ios, android, mweb, tv, web
- Search also falls back to Piped if yt-dlp fails
- Requirements pin recent yt-dlp

## Local test
```bash
pip install -r requirements.txt
python app.py
# open http://127.0.0.1:5000
```
