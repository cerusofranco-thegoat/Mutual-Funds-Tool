"""Gunicorn configuration for production deployment."""

bind = "0.0.0.0:5000"
workers = 1  # Must be 1 since we use in-memory job tracking and threading
threads = 4
timeout = 600  # 10 minutes - analysis can be slow
accesslog = "-"
errorlog = "-"
loglevel = "info"
