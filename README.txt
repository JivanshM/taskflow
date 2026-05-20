TaskFlow - Team Task Manager
============================

Live Application URL
--------------------
Sorry for the inconvenience. The previous Railway deployment link expired because the Railway trial for that deployment ended, so the application has been redeployed and the updated live URL is listed below.

https://web-production-53a36.up.railway.app/

GitHub Repository
-----------------
https://github.com/JivanshM/taskflow

Project Overview
----------------
TaskFlow is a full-stack team task manager where users can create projects, invite team members, assign tasks, and track progress through a clean dashboard. The app includes authentication, project/team management, task workflows, status tracking, overdue task visibility, and role-based access control for Admin and Member users.

The interface is intentionally minimal and Apple-like, with a focused dashboard, clean project forms, simple task boards, and responsive layouts for desktop and mobile.

Key Features
------------
- Authentication: users can sign up, log in, and access protected routes using token-based authentication.
- Project management: authenticated users can create projects and view projects they own or are part of.
- Team management: project admins can add members by username/email and manage access.
- Task management: users can create tasks, assign them to project members, set priority, set due dates, and update status.
- Status tracking: tasks move through To Do, In Progress, Review, and Done.
- Dashboard: users can view assigned tasks, completed tasks, overdue tasks, and project statistics.
- Role-based access control: Admin and Member permissions are enforced on the backend.
- REST APIs: all major app actions are handled through REST API endpoints.
- Database: SQLite is used for users, projects, members, tasks, and sessions.
- Deployment: deployed live on Railway.

Role-Based Access Control
-------------------------
Admin:
- Create, update, and delete project tasks.
- Add and remove project members.
- Assign tasks to project members.
- Delete projects if they are the project owner.

Member:
- View project details and task board.
- Update status/description only for tasks assigned to them or created by them.
- Cannot add/remove team members.
- Cannot delete projects.

Tech Stack
----------
- Backend: Python WSGI application
- Database: SQLite
- Frontend: HTML, CSS, JavaScript
- Authentication: secure token sessions
- Password security: PBKDF2 password hashing with salt
- Deployment: Railway
- Production server: Gunicorn

Project Structure
-----------------
- app.py: Backend server, REST APIs, authentication, validation, RBAC, SQLite schema, and static file serving.
- static/index.html: Frontend HTML entry point.
- static/css/style.css: Minimal responsive UI styling.
- static/js/app.js: Client-side app logic and API integration.
- requirements.txt: Production dependency list.
- Procfile: Railway/Gunicorn start command.
- railway.json: Railway deployment configuration.
- README.txt: Project documentation and submission details.

REST API Endpoints
------------------
Authentication:
- POST /api/auth/signup
- POST /api/auth/login
- GET /api/auth/me

Dashboard:
- GET /api/dashboard

Projects:
- GET /api/projects
- POST /api/projects
- GET /api/projects/:id
- PUT /api/projects/:id
- DELETE /api/projects/:id

Team Members:
- POST /api/projects/:id/members
- DELETE /api/projects/:id/members/:memberId
- PUT /api/projects/:id/members/:memberId/role

Tasks:
- GET /api/projects/:id/tasks
- POST /api/projects/:id/tasks
- GET /api/tasks/:id
- PUT /api/tasks/:id
- DELETE /api/tasks/:id

Users:
- GET /api/users/search?q=

Validations and Relationships
-----------------------------
- Usernames, emails, passwords, and full names are validated during signup.
- Duplicate usernames and emails are blocked.
- Project names are required.
- Task titles are required.
- Task status is limited to todo, in_progress, review, and done.
- Task priority is limited to low, medium, high, and urgent.
- Tasks can only be assigned to users who belong to the project.
- Removing a member unassigns their project tasks.
- Projects, members, tasks, users, and sessions are connected through SQLite relationships.

Local Setup
-----------
1. Install Python 3.11 or newer.
2. Install dependencies:
   pip install -r requirements.txt
3. Run the app:
   python app.py
4. Open in browser:
   http://localhost:8000

Railway Deployment
------------------
The project is deployed on Railway using the GitHub repository.

Railway start command:
gunicorn app:application

Deployment files:
- Procfile
- railway.json
- requirements.txt

Update Note
-----------
Sorry for the inconvenience. The previous Railway deployment link expired because the Railway trial for that deployment ended, so the application has been redeployed and the updated live URL is listed below.

Live deployed app:
https://web-production-53a36.up.railway.app/
