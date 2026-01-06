FROM python:3.12-slim
WORKDIR /app
RUN pip install fastapi uvicorn[standard] telethon pydantic "qrcode[pil]"
COPY app.py .
EXPOSE 8099
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8099"]
