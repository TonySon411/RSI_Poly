module.exports = {
  apps: [
    {
      name: "rsi-dashboard",
      cwd: __dirname,
      script: ".venv/bin/python",
      args: "app.py",
      interpreter: "none",
      instances: 1, // do NOT scale this beyond 1 -- see Deploy.md's "Single instance only" note
      exec_mode: "fork",
      autorestart: true,
      restart_delay: 5000,
      max_restarts: 10,
      env: { PYTHONUNBUFFERED: "1" },
      out_file: "logs/pm2-out.log",
      error_file: "logs/pm2-error.log",
      merge_logs: true,
      time: true,
    },
    {
      name: "rsi-recorder",
      cwd: __dirname,
      script: ".venv/bin/python",
      args: "recordData.py",
      interpreter: "none",
      instances: 1, // do NOT scale this beyond 1 -- see Deploy.md's "Single instance only" note
      exec_mode: "fork",
      autorestart: true,
      restart_delay: 5000,
      max_restarts: 10,
      env: { PYTHONUNBUFFERED: "1" },
      out_file: "logs/pm2-recorder-out.log",
      error_file: "logs/pm2-recorder-error.log",
      merge_logs: true,
      time: true,
    },
  ],
};
