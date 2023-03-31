import os
import time
import logging
import traceback
from threading import Thread

from flask import Flask, request, jsonify
from flask_caching import Cache
import atexit
from apscheduler.schedulers.background import BackgroundScheduler

import openai
from utils import num_tokens_from_messages


NUM_MAX_TOKEN = 4096
KAKAO_API_TIMEOUT = 5
WAIT_TIME = KAKAO_API_TIMEOUT - 0.5  # chatgpt 응답 기다리는 시간
openai.api_key = os.getenv("OPENAI_API_KEY")

config = {
    "DEBUG": True,
    "CACHE_TYPE": "FileSystemCache",
    "CACHE_DEFAULT_TIMEOUT": 60 * 30,
    "CACHE_THRESHOLD": 10000,
    "CACHE_DIR": "cache",
}

app = Flask(__name__)
app.config.from_mapping(config)
cache = Cache(app)


scheduler = BackgroundScheduler()
scheduler.add_job(func=cache.clear, trigger="interval", minutes=30)
scheduler.start()
atexit.register(lambda: scheduler.shutdown()) # Shut down when exiting the app


def run_chat_gpt(messages, user_id):
    gpt_message = None
    try:
        # https://platform.openai.com/docs/guides/chat/introduction
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0,
            request_timeout=120,
        )

        gpt_message = response["choices"][0]["message"]["content"]
        cache.set(f"{user_id}-response", gpt_message)

        # messages 캐시에 저장하기
        messages_cache = cache.get(f"{user_id}-messages")
        if messages_cache is not None:
            messages_cache.append({"role": "assistant", "content": gpt_message})
            cache.set(f"{user_id}-messages", messages_cache)

    except Exception as e:
        app.logger.error(f"run_chat_gpt error {e}\n{traceback.format_exc()}")

    if gpt_message is None:
        cache.set(f"{user_id}-response", "[ERROR]")


def init_user_messages(user_id):
    system_prompts = [
        {"role": "system", "content": "당신은 카카오톡에서 대화하는 chatgpt 기반의 친절한 봇입니다."}
    ]
    cache.set(f"{user_id}-messages", system_prompts)


def update_messages(user_id, user_text):
    """
    messages example:
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Who won the world series in 2020?"},
        {"role": "assistant", "content": "The Los Angeles Dodgers won the World Series in 2020."},
        {"role": "user", "content": "Where was it played?"}
    ]
    """
    new_message = {"role": "user", "content": user_text}
    messages = cache.get(f"{user_id}-messages")  # 이전 메세지 가져오기
    messages.append(new_message)  # 새로운 메세지 추가

    # max token 개수 넘으면 오래된 메세지 제거하기
    while True:
        num_tokens = num_tokens_from_messages(messages)
        if num_tokens > NUM_MAX_TOKEN:
            messages.pop(1)
        else:
            break

    cache.set(f"{user_id}-messages", messages)  # 캐시 저장하기
    return messages, num_tokens


def kakao_response_text(text):
    # https://i.kakao.com/docs/skill-response-format#simpletext
    return {
        "version": "2.0",
        "template": {"outputs": [{"simpleText": {"text": text}}]},
    }


def kakao_response_button():
    # https://i.kakao.com/docs/skill-response-format#quickreplies
    return {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": "답변을 준비하고 있습니다."}}],
            "quickReplies": [
                {"messageText": "답변 확인 하기", "action": "message", "label": "답변 확인 하기"},
            ],
        },
    }


@app.route("/api/chatgpt", methods=["POST"])
def chatgpt():
    start_time = time.time()

    body = request.get_json()
    user_id = body["userRequest"]["user"]["id"]
    user_text = body["userRequest"]["utterance"].strip()

    user_info = cache.get(user_id)
    if user_info is None:
        # print(f"새로운 유저 init cache: {user_id}")
        cache.set(user_id, {"user_id": user_id, "chat_limit": 100})  # TODO: limit 구현
        cache.set(f"{user_id}-response", "[INIT]")
        init_user_messages(user_id)

    if user_text == "답변 확인 하기":
        gpt_message = cache.get(f"{user_id}-response")
        if gpt_message == "[RUNNING]":
            while True:  # 최대 WAIT_TIME 만큼 답변 기다리기
                gpt_message = cache.get(f"{user_id}-response")
                if (gpt_message != "[RUNNING]") or (time.time() - start_time >= WAIT_TIME):
                    break
                time.sleep(0.2)

        if gpt_message == "[RUNNING]":
            response = kakao_response_button()
        elif gpt_message == "[INIT]":
            response = kakao_response_text("질문을 입력 해주세요.")
        elif gpt_message == "[ERROR]":
            response = kakao_response_text("오류가 발생하였습니다.")
        else:
            response = kakao_response_text(gpt_message)

    elif user_text == "새로운 대화":
        init_user_messages(user_id)
        response = kakao_response_text("새로운 대화를 시작합니다.")

    else:
        if cache.get(f"{user_id}-response") == "[RUNNING]":
            response = kakao_response_button()
            return response

        messages, num_tokens = update_messages(user_id, user_text)
        if num_tokens > NUM_MAX_TOKEN:
            response = kakao_response_text("너무 긴 입력입니다. 다시 입력해주세요.")
            init_user_messages(user_id)
            return response

        # run chat gpt
        cache.set(f"{user_id}-response", "[RUNNING]")
        thread = Thread(target=run_chat_gpt, args=(messages, user_id))
        thread.daemon = True
        thread.start()

        while True:  # 최대 WAIT_TIME 만큼 답변 기다리기
            gpt_message = cache.get(f"{user_id}-response")
            if (gpt_message != "[RUNNING]") or (time.time() - start_time >= WAIT_TIME):
                break
            time.sleep(0.2)

        if gpt_message == "[RUNNING]":
            response = kakao_response_button()  # "답변을 준비하고 있습니다" 버튼
        else:
            response = kakao_response_text(gpt_message)  # chatgpt 답변

    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, threaded=True)

else:
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
