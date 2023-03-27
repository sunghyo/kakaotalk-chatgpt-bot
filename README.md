# kakaotalk-chatgpt-bot

- 카카오톡에서 ChatGPT와 대화할 수 있는 챗봇을 구성하는 프로젝트입니다.
- Flask와 flask_caching을 이용해서 최소한의 기능만 구현을 했습니다.


## 구현된 기능

- [x] 카카오톡 챗봇 api 5초 timeout 고려

## 사용 예시

- OpenGPT (챗지피티) 봇에서 확인해볼 수 있습니다.
    - http://pf.kakao.com/_rhyxcxj

<img src="https://user-images.githubusercontent.com/7691845/228002286-dc654651-dc8e-4cc0-9cc8-73861a7bed38.jpeg" width=300/>


## 라이브러리 설치

```bash
pip install flask flask_caching tiktoken gunicorn
pip install --upgrade openai
```

## 사용하기

### openai api 키 등록

```bash
export OPENAI_API_KEY="dladmlfhTjensrmfwkdlqslek..."
# or app.py의 openai.api_key에 입력
```

### 봇 flask 실행하기

```bash
# app.py에서 port 설정
python app.py

# or
gunicorn app:app \
    --workers 4 \
    --bind 0.0.0.0:5002 \
    --log-file ./gunicorn.log \
    --log-level DEBUG
```
