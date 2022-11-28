FROM python:3.10-alpine as base-image

ENV LANG=C.UTF-8

FROM base-image as build-wheels
RUN apk add alpine-sdk
WORKDIR /src
# hiredis requires gcc, so build the wheel here
RUN pip wheel hiredis -w /src/wheelhouse

FROM build-wheels as dev
WORKDIR /build
COPY --from=build-wheels /src/wheelhouse/ /build/wheelhouse/
RUN pip install wheelhouse/*

COPY requirements/ ./requirements
RUN pip install -r ./requirements/requirements_celery5.txt
RUN pip install -r ./requirements/requirements_test.txt

COPY celery_exporter/  ./celery_exporter/
COPY test/  ./test/
COPY tox.ini  ./tox.ini

FROM base-image as app
LABEL maintainer="Fabio Todaro <fbregist@gmail.com>"

WORKDIR /build
COPY --from=build-wheels /src/wheelhouse/ /build/wheelhouse/
RUN pip install wheelhouse/*
COPY requirements/ ./requirements
RUN pip install -r ./requirements/requirements_celery5.txt

WORKDIR /app
COPY celery_exporter/  /app/celery_exporter/

ENTRYPOINT ["python", "-m", "celery_exporter"]
CMD []

ARG BUILD_DATE
ARG DOCKER_REPO
ARG VERSION
ARG VCS_REF

LABEL org.label-schema.schema-version="1.0" \
      org.label-schema.build-date=$BUILD_DATE \
      org.label-schema.name=$DOCKER_REPO \
      org.label-schema.version=$VERSION \
      org.label-schema.description="Prometheus metrics exporter for Celery" \
      org.label-schema.vcs-ref=$VCS_REF \
      org.label-schema.vcs-url="https://github.com/grafana/celery-exporter"

EXPOSE 9540
