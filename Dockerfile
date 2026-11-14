FROM python:3.14-slim
WORKDIR /kodee
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 kodee
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY __init__.py config.py main.py gunicorn.conf.py ./
COPY bot/ ./bot/
COPY db/ ./db/
COPY web/ ./web/
RUN mkdir -p logs certificates instance /var/data/productImgs \
    && chown -R kodee:kodee logs certificates instance /var/data
ENV FLASK_APP=main.py PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PRODUCT_IMAGES_DIR=/var/data/productImgs
USER kodee
CMD ["gunicorn", "-c", "gunicorn.conf.py", "main:app"]
