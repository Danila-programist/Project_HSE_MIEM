FROM python:3.12-slim-bookworm AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends doxygen graphviz \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /source
COPY Doxyfile ./
COPY app ./app
COPY alembic ./alembic
COPY docs/doxygen ./docs/doxygen
COPY docs/tools ./docs/tools
RUN mkdir -p build/doxygen \
    && doxygen Doxyfile \
    && mkdir -p build/doxygen/html/downloads \
    && cp build/doxygen/rtf/refman.rtf build/doxygen/html/downloads/isudo.rtf \
    && tar -czf build/doxygen/html/downloads/isudo-rtf.tar.gz -C build/doxygen rtf

FROM nginx:stable-alpine
COPY --from=builder /source/build/doxygen/html /usr/share/nginx/html
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
EXPOSE 80
