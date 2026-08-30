# This file builds the custom container image for Apache Airflow used by your safeeatsnyc project. 
# It starts with the official Airflow image, adds your project's custom python dependencies, and makes sure they are installed securely under the correct user permissions.

ARG AIRFLOW_VERSION=3.3.1
FROM apache/airflow:${AIRFLOW_VERSION}

ARG AIRFLOW_VERSION
COPY --chown=airflow:root requirements.txt /opt/airflow/requirements-safeeats.txt
RUN pip install --no-cache-dir \
    "apache-airflow==${AIRFLOW_VERSION}" \
    -r /opt/airflow/requirements-safeeats.txt


# COPY --chown=airflow:root requirements.txt /opt/airflow/requirements-safeeats.txt -
# Copies your local Python requirements file (which lists all packages like pandas, requests, boto3, etc. needed for SafeEats) into the container, ensuring it is owned by the airflow user for security.