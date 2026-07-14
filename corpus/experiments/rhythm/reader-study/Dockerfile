FROM python:3.13-slim

WORKDIR /study
COPY app.py index.html stimuli.json ./

ENV PYTHONUNBUFFERED=1
ENV READER_STUDY_DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8765

CMD ["python", "app.py", "--host", "0.0.0.0", "--port", "8765"]
