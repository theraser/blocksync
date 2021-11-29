ARG TAG

FROM python:${TAG}
RUN apt update && DEBIAN_FRONTEND=noninteractive apt upgrade -y
RUN pip install --upgrade pip
COPY *.py /opt/job/
WORKDIR /opt/job

ENTRYPOINT ["python", "-OO", "./blocksync.py", "--blocksize", "4194304" ]
