FROM python:alpine
ADD app /app
WORKDIR /app
RUN pip install -r requirements.txt
RUN apk update && apk add curl
RUN apk add docker