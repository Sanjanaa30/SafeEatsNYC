# This file builds the custom container image for Apache Airflow used by your safeeatsnyc project. 
# It starts with the official Airflow image, adds your project's custom python dependencies, and makes sure they are installed securely under the correct user permissions.

ARG AIRFLOW_VERSION=3.3.1
FROM python:3.13-slim AS dbt-dependency-builder
RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY warehouse/requirements.txt /tmp/requirements-dbt.txt
RUN pip wheel --no-cache-dir --wheel-dir /tmp/dbt-wheels \
    -r /tmp/requirements-dbt.txt

FROM eclipse-temurin:21-jre-jammy AS java-runtime
FROM apache/airflow:${AIRFLOW_VERSION}

ARG AIRFLOW_VERSION
USER root
COPY --from=java-runtime /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH="${JAVA_HOME}/bin:${PATH}"
USER airflow
COPY --chown=airflow:root requirements.txt /opt/airflow/requirements-safeeats.txt
RUN pip install --no-cache-dir \
    "apache-airflow==${AIRFLOW_VERSION}" \
    -r /opt/airflow/requirements-safeeats.txt
COPY --chown=airflow:root --from=dbt-dependency-builder /tmp/dbt-wheels /tmp/dbt-wheels
RUN pip install --no-cache-dir /tmp/dbt-wheels/* \
    && rm -rf /tmp/dbt-wheels


# COPY --chown=airflow:root requirements.txt /opt/airflow/requirements-safeeats.txt -
# Copies your local Python requirements file (which lists all packages like pandas, requests, boto3, etc. needed for SafeEats) into the container, ensuring it is owned by the airflow user for security.
