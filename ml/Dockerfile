FROM python:3.13-slim

WORKDIR /opt/safeeats

COPY ml/requirements.txt /tmp/requirements-ml.txt
RUN pip install --no-cache-dir -r /tmp/requirements-ml.txt

ENTRYPOINT ["python"]
CMD ["-m", "ml.prepare_training_data", "--help"]
