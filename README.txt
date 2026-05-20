TaskFlow

TaskFlow is a minimal full-stack team task manager with:
- Authentication
- Projects and team membership
- Task creation, assignment, and status tracking
- Dashboard with assigned and overdue work
- Role-based access control for Admin and Member

Stack
- Backend: Python standard library WSGI app
- Database: SQLite
- Frontend: Vanilla HTML, CSS, and JavaScript
- Production server: Gunicorn

Run locally
1. Install Python 3.11+.
2. Start the app:
   python app.py
3. Open:
   http://localhost:8000

Key files
- app.py
- static/index.html
- static/css/style.css
- static/js/app.js
- requirements.txt
- Procfile
- railway.json

Railway deployment
1. Push the project to GitHub.
2. Create a new Railway project from the repo.
3. Railway will use the Procfile / railway.json start command:
   gunicorn app:application
4. Open the generated Railway URL.

Quick deploy commands
1. git init
2. git add .
3. git commit -m "Build TaskFlow full-stack app"
4. Create an empty GitHub repository.
5. git remote add origin YOUR_GITHUB_REPO_URL
6. git branch -M main
7. git push -u origin main
8. In Railway, choose New Project -> Deploy from GitHub repo -> select this repo.

Submission checklist
- Live URL: add your Railway URL
- GitHub repo: add your repo URL
- README: this file
- Demo video: show signup, login, project creation, member invite, task creation, status updates, and RBAC
