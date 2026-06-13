FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY broker.py runner_driver.py docker_driver.py vm_driver.py .
CMD ["python", "broker.py"]
