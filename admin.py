<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Admin Dashboard – Solace</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', sans-serif; background: #f0f2f5; color: #333; }

    /* Sidebar */
    .sidebar {
      width: 220px; position: fixed; top: 0; left: 0; height: 100vh;
      background: #1e2a3a; color: #cdd9e5; display: flex; flex-direction: column;
    }
    .sidebar .logo { padding: 24px 20px; font-size: 1.3rem; font-weight: 700;
      color: #fff; border-bottom: 1px solid #2e3f52; }
    .sidebar nav a {
      display: block; padding: 13px 20px; color: #aab8c8; text-decoration: none;
      font-size: 0.9rem; transition: background 0.15s;
    }
    .sidebar nav a:hover, .sidebar nav a.active { background: #2e3f52; color: #fff; }
    .sidebar nav .section-label {
      padding: 14px 20px 6px; font-size: 0.7rem; text-transform: uppercase;
      letter-spacing: 1px; color: #5f7a90;
    }

    /* Main */
    .main { margin-left: 220px; padding: 30px; }
    .page-title { font-size: 1.6rem; font-weight: 700; margin-bottom: 6px; }
    .page-sub { color: #666; font-size: 0.9rem; margin-bottom: 28px; }

    /* Stat cards */
    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 18px; margin-bottom: 30px; }
    .stat-card {
      background: #fff; border-radius: 12px; padding: 22px 24px;
      box-shadow: 0 2px 8px rgba(0,0,0,.06);
    }
    .stat-card .label { font-size: 0.78rem; color: #888; text-transform: uppercase; letter-spacing: .5px; }
    .stat-card .value { font-size: 2rem; font-weight: 700; margin-top: 6px; }
    .stat-card.blue .value { color: #2563eb; }
    .stat-card.green .value { color: #16a34a; }
    .stat-card.orange .value { color: #ea580c; }
    .stat-card.purple .value { color: #7c3aed; }
    .stat-card.pink .value { color: #db2777; }

    /* Tables */
    .card { background: #fff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,.06); margin-bottom: 24px; overflow: hidden; }
    .card-header { padding: 18px 24px; font-weight: 600; font-size: 1rem; border-bottom: 1px solid #f0f0f0; display: flex; justify-content: space-between; align-items: center; }
    .card-header a { font-size: 0.82rem; color: #2563eb; text-decoration: none; }
    table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
    th { background: #f8f9fb; padding: 10px 18px; text-align: left; font-weight: 600; color: #555; font-size: 0.78rem; text-transform: uppercase; }
    td { padding: 11px 18px; border-top: 1px solid #f2f2f2; }

    .badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; }
    .badge.pending { background: #fef3c7; color: #92400e; }
    .badge.done    { background: #d1fae5; color: #065f46; }
    .badge.admin   { background: #ede9fe; color: #5b21b6; }
    .badge.user    { background: #e0f2fe; color: #075985; }

    /* Flash */
    .flash { background: #d1fae5; border-left: 4px solid #10b981; padding: 12px 18px;
      border-radius: 6px; margin-bottom: 20px; font-size: 0.88rem; }

    .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
    @media (max-width: 900px) { .grid2 { grid-template-columns: 1fr; } }
  </style>
</head>
<body>

<div class="sidebar">
  <div class="logo">⚡ Solace Admin</div>
  <nav>
    <div class="section-label">Overview</div>
    <a href="/admin" class="active">📊 Dashboard</a>
    <div class="section-label">Manage</div>
    <a href="/admin/users">👥 Users</a>
    <a href="/admin/tasks">✅ Tasks</a>
    <a href="/admin/posts">📝 Posts</a>
    <div class="section-label">App</div>
    <a href="/tracker">🏠 Back to App</a>
    <a href="/logout">🚪 Logout</a>
  </nav>
</div>

<div class="main">
  <div class="page-title">Dashboard</div>
  <div class="page-sub">Welcome back, Admin. Here's what's happening.</div>

  {% with messages = get_flashed_messages() %}
    {% if messages %}
      {% for m in messages %}<div class="flash">{{ m }}</div>{% endfor %}
    {% endif %}
  {% endwith %}

  <!-- Stats -->
  <div class="stats">
    <div class="stat-card blue">
      <div class="label">Total Users</div>
      <div class="value">{{ total_users }}</div>
    </div>
    <div class="stat-card purple">
      <div class="label">Mood Logs</div>
      <div class="value">{{ total_moods }}</div>
    </div>
    <div class="stat-card orange">
      <div class="label">Total Tasks</div>
      <div class="value">{{ total_tasks }}</div>
    </div>
    <div class="stat-card green">
      <div class="label">Done Tasks</div>
      <div class="value">{{ done_tasks }}</div>
    </div>
    <div class="stat-card pink">
      <div class="label">Posts</div>
      <div class="value">{{ total_posts }}</div>
    </div>
  </div>

  <div class="grid2">
    <!-- Recent Users -->
    <div class="card">
      <div class="card-header">Recent Users <a href="/admin/users">View all →</a></div>
      <table>
        <thead><tr><th>Username</th><th>Email</th><th>Role</th></tr></thead>
        <tbody>
          {% for u in recent_users %}
          <tr>
            <td><a href="/admin/users/{{ u.id }}" style="color:#2563eb;text-decoration:none">{{ u.username }}</a></td>
            <td>{{ u.email }}</td>
            <td><span class="badge {{ 'admin' if u.is_admin else 'user' }}">{{ 'Admin' if u.is_admin else 'User' }}</span></td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <!-- Recent Moods -->
    <div class="card">
      <div class="card-header">Recent Mood Logs</div>
      <table>
        <thead><tr><th>User</th><th>Mood</th><th>Time</th></tr></thead>
        <tbody>
          {% for m in recent_moods %}
          <tr>
            <td>{{ m.username }}</td>
            <td>{{ m.mood }}</td>
            <td style="color:#888;font-size:0.82rem">{{ m.timestamp }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>

    <!-- Recent Tasks -->
    <div class="card">
      <div class="card-header">Recent Tasks <a href="/admin/tasks">View all →</a></div>
      <table>
        <thead><tr><th>Title</th><th>Status</th><th>Created</th></tr></thead>
        <tbody>
          {% for t in recent_tasks %}
          <tr>
            <td>{{ t.title }}</td>
            <td><span class="badge {{ t.status }}">{{ t.status }}</span></td>
            <td style="color:#888;font-size:0.82rem">{{ t.created_at }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</div>

</body>
</html>