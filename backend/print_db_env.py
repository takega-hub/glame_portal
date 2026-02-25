import os
from dotenv import load_dotenv

load_dotenv()

keys = [
    "DATABASE_URL",
    "DB_HOST",
    "DB_PORT",
    "DB_USER",
    "DB_PASSWORD",
    "DB_NAME",
]

for k in keys:
    v = os.getenv(k)
    if v is None:
        print(f"{k}=<unset>")
    elif k == "DB_PASSWORD":
        print(f"{k}=<set> (len={len(v)})")
    else:
        print(f"{k}={v!r}")

