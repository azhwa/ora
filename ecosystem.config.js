const path = require("path");

module.exports = {
  apps: [
    {
      name: "oracle-hunter",
      cwd: __dirname,
      script: path.join(__dirname, "hunter.py"),
      interpreter: path.join(__dirname, ".venv", "bin", "python3"),
      autorestart: true,
      max_restarts: 100,
      restart_delay: 5000,
      watch: false,
      out_file: path.join(__dirname, "oracle_hunter.log"),
      error_file: path.join(__dirname, "oracle_hunter.log"),
      merge_logs: true,
      env: {
        PYTHONUNBUFFERED: "1"
      }
    }
  ]
};
