# Smart Surplus Food Allocation & Redistribution System
Flask REST API + SQLite (backend) and React/Vite (frontend).

## Run (two terminals)
Backend:  cd backend
          python -m venv venv ; venv\Scripts\activate  (Mac/Linux: source venv/bin/activate)
          pip install -r requirements.txt
          python app.py                  -> http://127.0.0.1:5000  (creates backend/surplus.db on first run)
Frontend: cd frontend
          npm install
          npm run dev                    -> open http://localhost:5173

## Demo accounts
admin@demo.com / admin123 (everything + Settings), donor@demo.com / demo123, recipient@demo.com / demo123
Anyone can register as donor or recipient. Set SECRET_KEY and change the admin password before real use.

## Notes
- Road distance uses the public OSRM server and addresses use OpenStreetMap Nominatim: both need internet and are
  rate-limited demo services. Offline, distances fall back to straight-line x 1.3 (shown as "est.").
- Allocation runs automatically on every new donation/recipient and every `auto_interval_s` seconds.
- Delete backend/surplus.db to reset all data.
