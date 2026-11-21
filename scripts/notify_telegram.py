#!/usr/bin/env python3
"""Send only newly discovered freelance jobs to a Telegram chat."""
import html
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

FEED = Path("jobs-feed.json")
STATE = Path("notification-state.json")
MAX_PER_RUN = 5

def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default

def telegram_send(token, chat_id, text):
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError("Telegram API rejected sendMessage")

def send_test_notification():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in GitHub Actions secrets.")
    test = read_json(Path("test-notification.json"), {})
    title = html.escape((test.get("title") or "Тестовый заказ")[:180])
    summary = html.escape((test.get("summary") or "").strip()[:420])
    budget = test.get("budget") or 0
    budget_line = f"💰 Бюджет: <b>{html.escape(str(budget))}</b>" if budget else "💰 Бюджет не указан"
    message = (
        "🧪 <b>ТЕСТ УВЕДОМЛЕНИЙ — это не реальный заказ</b>\n\n"
        f"<b>{title}</b>\n"
        "📌 Источник: Тест системы\n"
        f"{budget_line}\n"
        + (f"\n{summary}\n" if summary else "")
        + "\nЕсли ты видишь это сообщение, доставка в Telegram работает."
    )
    telegram_send(token, chat_id, message)
    print("Test notification delivered.")


def main():
    if Path("test-notification.json").exists():
        send_test_notification()
        return

    feed = read_json(FEED, {"jobs": []})
    jobs = feed.get("jobs") or []
    state = read_json(STATE, None)

    # First run establishes a baseline. It deliberately does not flood the chat
    # with historical listings already present in the feed.
    if state is None:
        STATE.write_text(json.dumps({
            "known_ids": [job.get("id") for job in jobs if job.get("id")],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Initialized notification baseline with {len(jobs)} existing jobs.")
        return

    known = set(state.get("known_ids") or [])
    fresh = [job for job in jobs if job.get("id") and job["id"] not in known]
    fresh.sort(key=lambda job: job.get("publishedAt") or "", reverse=True)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if fresh and (not token or not chat_id):
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in GitHub Actions secrets.")

    sent_ids = []
    for job in fresh[:MAX_PER_RUN]:
        title = html.escape((job.get("title") or "Новый заказ")[:180])
        source = html.escape(job.get("source") or "Биржа")
        summary = html.escape((job.get("summary") or "").strip()[:420])
        budget = job.get("budget") or 0
        budget_line = f"💰 Бюджет: <b>{html.escape(str(budget))}</b>" if budget else "💰 Бюджет не указан"
        url = html.escape(job.get("url") or "", quote=True)
        message = (
            "🆕 <b>Новый фриланс-заказ</b>\n\n"
            f"<b>{title}</b>\n"
            f"📌 Источник: {source}\n"
            f"{budget_line}\n"
            + (f"\n{summary}\n" if summary else "\n")
            + (f'\n<a href="{url}">Открыть заказ</a>' if url else "")
        )
        telegram_send(token, chat_id, message)
        sent_ids.append(job["id"])
        print("Sent:", job["id"])

    # Mark only successfully delivered jobs. Leave excess fresh jobs for next run.
    known.update(sent_ids)
    # Keep IDs still present in the current feed plus the IDs sent this run.
    current_ids = {job.get("id") for job in jobs if job.get("id")}
    state["known_ids"] = sorted((known & current_ids) | set(sent_ids))
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"New jobs: {len(fresh)}; delivered: {len(sent_ids)}.")

if __name__ == "__main__":
    main()
