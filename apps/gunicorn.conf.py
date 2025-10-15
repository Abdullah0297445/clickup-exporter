import os

workers = 4
worker_temp_dir = "/dev/shm"
timeout = int(os.environ.get("REQUEST_TIMEOUT", 60))
bind = f"0.0.0.0:{int(os.environ.get('DJANGO_PORT'))}"
wsgi_app = "core.asgi"
max_requests = 10000
max_requests_jitter = 100
forwarded_allow_ips = "*"
loglevel = "info"
accesslog = "-"
errorlog = "-"
capture_output = True
proc_name = "clickup-exporter-gunicorn"
limit_request_fields = 50
worker_class = "uvicorn_worker.UvicornWorker"
