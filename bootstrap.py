import os
import subprocess
import time
import sys

REPO_URL = "https://github.com/privatejobwallah2002-hue/vdapi.git"

def run():
    if not os.path.exists("vd"):
        subprocess.run(["git", "clone", REPO_URL], check=True)
    else:
        subprocess.run(["git", "-C", "vd", "pull"])

    os.chdir("vd")

    print("Libraries install kar raha hoon...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"])
    subprocess.run(["apt-get", "install", "-y", "-qq", "ffmpeg"])

    print("Deno install kar raha hoon...")
    subprocess.run("curl -fsSL https://deno.land/install.sh | sh -s -- -y", shell=True)
    os.environ["PATH"] = f"{os.path.expanduser('~/.deno/bin')}:{os.environ['PATH']}"

    from dotenv import dotenv_values
    env = dotenv_values(".env")

    print("Local Bot API Server start kar raha hoon...")
    subprocess.Popen(
        f"curl -L https://github.com/jakbin/telegram-bot-api-binary/raw/main/run.sh | bash -s {env['API_ID']} {env['API_HASH']}",
        shell=True
    )
    time.sleep(10)

    print("Bot start ho raha hai — LIVE ho gaya!")
    subprocess.run([sys.executable, "bot.py"])

run()
