# Application de démonstration des tests de bout en bout de DevOps Builder.
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
USER 10001
EXPOSE 8000
CMD ["python", "app.py"]
