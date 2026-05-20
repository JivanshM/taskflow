const state = {
    token: localStorage.getItem("taskflow_token"),
    user: null,
    view: "dashboard",
    authMode: "login",
    dashboard: null,
    projects: [],
    activeProject: null,
    activeTasks: [],
};

function initials(name = "") {
    return name.split(" ").filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join("") || "?";
}

function fmtDate(value) {
    if (!value) return "No date";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "No date";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

async function api(path, options = {}) {
    const headers = options.headers || {};
    headers["Content-Type"] = "application/json";
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    const response = await fetch(path, { ...options, headers });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || data.message || data.errors?.general || "Request failed");
    return data;
}

function saveToken(token) {
    state.token = token;
    if (token) localStorage.setItem("taskflow_token", token);
    else localStorage.removeItem("taskflow_token");
}

function logout() {
    saveToken(null);
    state.user = null;
    state.view = "dashboard";
    render();
}

function app() {
    return document.getElementById("app");
}

function button(label, className = "btn", onclick = "") {
    return `<button class="${className}" ${onclick ? `onclick="${onclick}"` : ""}>${label}</button>`;
}

function renderAuth(message = "") {
    const isSignup = state.authMode === "signup";
    app().innerHTML = `
        <div class="auth-wrap">
            <div class="auth-card">
                <div class="auth-mark">TF</div>
                <h1 class="auth-title">${isSignup ? "Create your workspace" : "Welcome back"}</h1>
                <p class="subtitle">${isSignup ? "Start a clean project board for your team." : "Sign in to manage projects, tasks, and team progress."}</p>
                <div class="toggle">
                    <button class="${state.authMode === "login" ? "active" : ""}" onclick="setAuthMode('login')">Login</button>
                    <button class="${state.authMode === "signup" ? "active" : ""}" onclick="setAuthMode('signup')">Signup</button>
                </div>
                ${message ? `<div class="message">${message}</div>` : ""}
                <form onsubmit="submitAuth(event)">
                    ${state.authMode === "signup" ? `<div><label>Full name</label><input name="full_name" required minlength="2"></div>` : ""}
                    <div><label>${state.authMode === "login" ? "Username or email" : "Username"}</label><input name="username" required></div>
                    ${state.authMode === "signup" ? `<div><label>Email</label><input name="email" type="email" required></div>` : ""}
                    <div><label>Password</label><input name="password" type="password" minlength="6" required></div>
                    <button class="btn" type="submit">${state.authMode === "login" ? "Sign in" : "Create account"}</button>
                </form>
                <div class="auth-foot">
                    <span>SQLite</span>
                    <span>REST API</span>
                    <span>Admin / Member</span>
                </div>
            </div>
        </div>
    `;
}

function setAuthMode(mode) {
    state.authMode = mode;
    renderAuth();
}

async function submitAuth(event) {
    event.preventDefault();
    const form = new FormData(event.target);
    const payload = Object.fromEntries(form.entries());
    try {
        const route = state.authMode === "login" ? "/api/auth/login" : "/api/auth/signup";
        const data = await api(route, { method: "POST", body: JSON.stringify(payload) });
        saveToken(data.token);
        state.user = data.user;
        await loadDashboard();
        render();
    } catch (error) {
        renderAuth(error.message);
    }
}

function shell(content) {
    const user = state.user;
    return `
        <div class="shell">
            <aside class="sidebar">
                <div class="brand">Task<span>Flow</span></div>
                <div class="nav">
                    <button class="${state.view === "dashboard" ? "active" : ""}" onclick="go('dashboard')">Dashboard</button>
                    <button class="${state.view === "projects" ? "active" : ""}" onclick="go('projects')">Projects</button>
                </div>
                <div class="sidebar-footer">
                    <div class="user-chip">
                        <div class="avatar" style="background:${user.avatar_color}">${initials(user.full_name)}</div>
                        <div>
                            <div><strong>${escapeHtml(user.full_name)}</strong></div>
                            <div class="helper">@${escapeHtml(user.username)}</div>
                        </div>
                    </div>
                    ${button("Logout", "ghost", "logout()")}
                </div>
            </aside>
            <main class="main">
                <div class="mobile-nav">
                    <button class="${state.view === "dashboard" ? "active" : ""}" onclick="go('dashboard')">Dashboard</button>
                    <button class="${state.view === "projects" ? "active" : ""}" onclick="go('projects')">Projects</button>
                    <button onclick="logout()">Logout</button>
                </div>
                ${content}
            </main>
        </div>
    `;
}

function renderDashboard() {
    const data = state.dashboard;
    const stats = data.stats;
    const content = `
        <div class="header">
            <div>
                <h1 class="title">Dashboard</h1>
                <p class="subtitle">Track your workload, overdue items, and recent task movement.</p>
            </div>
            ${button("New project", "btn", "go('projects')")}
        </div>
        <section class="grid-4">
            <div class="stat"><div class="stat-label">Projects</div><div class="stat-value">${stats.total_projects}</div></div>
            <div class="stat"><div class="stat-label">Assigned tasks</div><div class="stat-value">${stats.total_tasks}</div></div>
            <div class="stat"><div class="stat-label">Completed</div><div class="stat-value">${stats.completed}</div></div>
            <div class="stat"><div class="stat-label">Overdue</div><div class="stat-value">${stats.overdue}</div></div>
        </section>
        <section class="grid-2" style="margin-top:18px;">
            <div class="panel">
                <div class="spread">
                    <h3>Recent tasks</h3>
                    <span class="chip">${stats.completion_rate}% done</span>
                </div>
                <div class="stack">
                    ${data.recent_tasks.length ? data.recent_tasks.map(taskSnippet).join("") : `<p class="helper">No assigned tasks yet.</p>`}
                </div>
            </div>
            <div class="panel">
                <div class="spread">
                    <h3>Overdue</h3>
                    <span class="badge overdue">${data.overdue_tasks.length}</span>
                </div>
                <div class="stack">
                    ${data.overdue_tasks.length ? data.overdue_tasks.map(taskSnippet).join("") : `<p class="helper">Nothing overdue.</p>`}
                </div>
            </div>
        </section>
    `;
    app().innerHTML = shell(content);
}

function taskSnippet(task) {
    return `
        <div class="task-card">
            <div class="spread">
                <h4>${escapeHtml(task.title)}</h4>
                <span class="badge ${task.status === "done" ? "done" : task.is_overdue ? "overdue" : task.status === "review" ? "review" : ""}">${prettyStatus(task.status)}</span>
            </div>
            <div class="row meta">
                <span>${escapeHtml(task.project_name || "No project")}</span>
                <span>${fmtDate(task.due_date)}</span>
            </div>
        </div>
    `;
}

function renderProjects() {
    const content = `
        <div class="header">
            <div>
                <h1 class="title">Projects</h1>
                <p class="subtitle">Create projects, invite teammates, and keep work moving.</p>
            </div>
        </div>
        <section class="grid-2">
            <div class="panel">
                <h3>Create project</h3>
                <form onsubmit="createProject(event)">
                    <div><label>Name</label><input name="name" required minlength="2"></div>
                    <div><label>Description</label><textarea name="description" placeholder="Short project summary"></textarea></div>
                    <button class="btn" type="submit">Create project</button>
                </form>
            </div>
            <div class="panel">
                <h3>Your projects</h3>
                <div class="project-grid">
                    ${state.projects.length ? state.projects.map(projectCard).join("") : `<p class="helper">No projects yet. Create your first one.</p>`}
                </div>
            </div>
        </section>
    `;
    app().innerHTML = shell(content);
}

function projectCard(project) {
    const stats = project.task_stats || {};
    return `
        <div class="project-card">
            <div class="spread">
                <div>
                    <h3>${escapeHtml(project.name)}</h3>
                    <p class="subtitle">${escapeHtml(project.description || "No description yet.")}</p>
                </div>
                <div class="avatar project-dot" style="background:${project.color};">•</div>
            </div>
            <div class="row meta">
                <span>${project.member_count} members</span>
                <span>${stats.total || 0} tasks</span>
                <span>${stats.overdue || 0} overdue</span>
            </div>
            ${button("Open project", "btn secondary", `openProject(${project.id})`)}
        </div>
    `;
}

function renderProjectDetail() {
    const project = state.activeProject;
    const grouped = {
        todo: state.activeTasks.filter((task) => task.status === "todo"),
        in_progress: state.activeTasks.filter((task) => task.status === "in_progress"),
        review: state.activeTasks.filter((task) => task.status === "review"),
        done: state.activeTasks.filter((task) => task.status === "done"),
    };
    const content = `
        <div class="header">
            <div>
                <h1 class="title">${escapeHtml(project.name)}</h1>
                <p class="subtitle">${escapeHtml(project.description || "No description yet.")}</p>
            </div>
            <div class="row">
                ${button("Back", "btn secondary", "go('projects')")}
                ${project.current_user_role === "admin" ? button("Delete project", "btn danger", `deleteProject(${project.id})`) : ""}
            </div>
        </div>
        <section class="grid-2">
            <div class="panel">
                <h3>Create task</h3>
                <form onsubmit="createTask(event)">
                    <div><label>Title</label><input name="title" required minlength="2"></div>
                    <div><label>Description</label><textarea name="description"></textarea></div>
                    <div class="split">
                        <div><label>Status</label>${statusSelect("status")}</div>
                        <div><label>Priority</label>${prioritySelect("priority")}</div>
                    </div>
                    <div class="split">
                        <div><label>Assignee</label>${memberSelect("assignee_id", project.members)}</div>
                        <div><label>Due date</label><input type="date" name="due_date"></div>
                    </div>
                    <button class="btn" type="submit">Create task</button>
                </form>
            </div>
            <div class="panel">
                <h3>Team</h3>
                ${project.current_user_role === "admin" ? `
                    <form onsubmit="addMember(event)">
                        <div><label>Username or email</label><input name="username" required></div>
                        <div><label>Role</label><select name="role"><option value="member">Member</option><option value="admin">Admin</option></select></div>
                        <button class="btn secondary" type="submit">Add member</button>
                    </form>
                ` : `<p class="helper">Members can view the team, while admins manage access.</p>`}
                <div class="stack" style="margin-top:16px;">
                    ${project.members.map(memberCard).join("")}
                </div>
            </div>
        </section>
        <section class="panel" style="margin-top:18px;">
            <div class="spread">
                <h3>Task board</h3>
                <span class="chip">${state.activeTasks.length} total</span>
            </div>
            <div class="task-columns">
                ${column("To do", grouped.todo)}
                ${column("In progress", grouped.in_progress)}
                ${column("Review", grouped.review)}
                ${column("Done", grouped.done)}
            </div>
        </section>
    `;
    app().innerHTML = shell(content);
}

function column(title, tasks) {
    return `<div class="column"><h3>${title}</h3><div class="stack">${tasks.length ? tasks.map(projectTaskCard).join("") : `<p class="helper">No tasks</p>`}</div></div>`;
}

function projectTaskCard(task) {
    const canDelete = state.activeProject.current_user_role === "admin" || task.creator_id === state.user.id;
    const canEdit = state.activeProject.current_user_role === "admin" || task.creator_id === state.user.id || task.assignee_id === state.user.id;
    return `
        <div class="task-card">
            <div class="spread">
                <h4>${escapeHtml(task.title)}</h4>
                <span class="badge ${task.priority}">${task.priority}</span>
            </div>
            <p class="subtitle">${escapeHtml(task.description || "No details.")}</p>
            <div class="row meta">
                <span>${task.assignee ? escapeHtml(task.assignee.full_name) : "Unassigned"}</span>
                <span>${fmtDate(task.due_date)}</span>
            </div>
            <div class="row">
                ${canEdit ? `<select onchange="quickStatus(${task.id}, this.value)">${["todo","in_progress","review","done"].map((status) => `<option value="${status}" ${task.status === status ? "selected" : ""}>${prettyStatus(status)}</option>`).join("")}</select>` : ""}
                ${canDelete ? button("Delete", "btn secondary", `deleteTask(${task.id})`) : ""}
            </div>
        </div>
    `;
}

function memberCard(member) {
    const owner = member.id === state.activeProject.owner_id;
    const canManage = state.user.id === state.activeProject.owner_id && !owner;
    const canRemove = state.activeProject.current_user_role === "admin" && !owner;
    return `
        <div class="member-card">
            <div class="spread">
                <div class="row">
                    <div class="avatar" style="background:${member.avatar_color}">${initials(member.full_name)}</div>
                    <div>
                        <h4>${escapeHtml(member.full_name)}</h4>
                        <div class="helper">${escapeHtml(member.email)}</div>
                    </div>
                </div>
                <div class="row">
                    ${canManage ? `<select onchange="changeRole(${member.id}, this.value)"><option value="member" ${member.role === "member" ? "selected" : ""}>Member</option><option value="admin" ${member.role === "admin" ? "selected" : ""}>Admin</option></select>` : `<span class="badge">${owner ? "owner" : member.role}</span>`}
                    ${canRemove ? button("Remove", "btn secondary", `removeMember(${member.id})`) : ""}
                </div>
            </div>
        </div>
    `;
}

function statusSelect(name) {
    return `<select name="${name}"><option value="todo">To do</option><option value="in_progress">In progress</option><option value="review">Review</option><option value="done">Done</option></select>`;
}

function prioritySelect(name) {
    return `<select name="${name}"><option value="low">Low</option><option value="medium" selected>Medium</option><option value="high">High</option><option value="urgent">Urgent</option></select>`;
}

function memberSelect(name, members) {
    return `<select name="${name}"><option value="">Unassigned</option>${members.map((member) => `<option value="${member.id}">${escapeHtml(member.full_name)}</option>`).join("")}</select>`;
}

function prettyStatus(status) {
    return status.replace("_", " ");
}

function escapeHtml(value = "") {
    return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
}

async function loadDashboard() {
    state.dashboard = await api("/api/dashboard");
}

async function loadProjects() {
    const data = await api("/api/projects");
    state.projects = data.projects;
}

async function openProject(id) {
    const data = await api(`/api/projects/${id}`);
    const tasks = await api(`/api/projects/${id}/tasks`);
    state.activeProject = data.project;
    state.activeTasks = tasks.tasks;
    state.view = "project";
    render();
}

async function go(view) {
    state.view = view;
    if (view === "dashboard") await loadDashboard();
    if (view === "projects") await loadProjects();
    render();
}

async function createProject(event) {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.target).entries());
    try {
        await api("/api/projects", { method: "POST", body: JSON.stringify(payload) });
        event.target.reset();
        await go("projects");
    } catch (error) {
        alert(error.message);
    }
}

async function createTask(event) {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.target).entries());
    if (payload.due_date) payload.due_date = new Date(payload.due_date).toISOString();
    try {
        await api(`/api/projects/${state.activeProject.id}/tasks`, { method: "POST", body: JSON.stringify(payload) });
        await openProject(state.activeProject.id);
    } catch (error) {
        alert(error.message);
    }
}

async function quickStatus(taskId, status) {
    try {
        await api(`/api/tasks/${taskId}`, { method: "PUT", body: JSON.stringify({ status }) });
        await openProject(state.activeProject.id);
    } catch (error) {
        alert(error.message);
    }
}

async function deleteTask(taskId) {
    if (!confirm("Delete this task?")) return;
    try {
        await api(`/api/tasks/${taskId}`, { method: "DELETE" });
        await openProject(state.activeProject.id);
    } catch (error) {
        alert(error.message);
    }
}

async function addMember(event) {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(event.target).entries());
    try {
        await api(`/api/projects/${state.activeProject.id}/members`, { method: "POST", body: JSON.stringify(payload) });
        event.target.reset();
        await openProject(state.activeProject.id);
    } catch (error) {
        alert(error.message);
    }
}

async function removeMember(memberId) {
    if (!confirm("Remove this member from the project?")) return;
    try {
        await api(`/api/projects/${state.activeProject.id}/members/${memberId}`, { method: "DELETE" });
        await openProject(state.activeProject.id);
    } catch (error) {
        alert(error.message);
    }
}

async function changeRole(memberId, role) {
    try {
        await api(`/api/projects/${state.activeProject.id}/members/${memberId}/role`, { method: "PUT", body: JSON.stringify({ role }) });
        await openProject(state.activeProject.id);
    } catch (error) {
        alert(error.message);
    }
}

async function deleteProject(projectId) {
    if (!confirm("Delete this project and all related tasks?")) return;
    try {
        await api(`/api/projects/${projectId}`, { method: "DELETE" });
        state.activeProject = null;
        state.activeTasks = [];
        await go("projects");
    } catch (error) {
        alert(error.message);
    }
}

async function bootstrap() {
    if (!state.token) {
        renderAuth();
        return;
    }
    try {
        const me = await api("/api/auth/me");
        state.user = me.user;
        await loadDashboard();
        render();
    } catch {
        logout();
    }
}

function render() {
    if (!state.token || !state.user) return renderAuth();
    if (state.view === "projects") return renderProjects();
    if (state.view === "project" && state.activeProject) return renderProjectDetail();
    return renderDashboard();
}

window.setAuthMode = setAuthMode;
window.submitAuth = submitAuth;
window.go = go;
window.logout = logout;
window.createProject = createProject;
window.openProject = openProject;
window.createTask = createTask;
window.quickStatus = quickStatus;
window.deleteTask = deleteTask;
window.addMember = addMember;
window.removeMember = removeMember;
window.changeRole = changeRole;
window.deleteProject = deleteProject;

bootstrap();
