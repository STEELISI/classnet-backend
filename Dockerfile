#
# 7.3.4 has a nasty bug that broke requests.get for us; and other
# things for others: https://foss.heptapod.net/pypy/pypy/-/issues/3441
#
#FROM pypy:3.7-slim-buster
FROM pypy:3.7-7.3.3-slim-buster

RUN \
  apt update -y \
  && apt install -y build-essential libpq-dev curl gpg \
  && rm -rf /var/lib/apt/lists/* \
  && pip install --upgrade pip setuptools wheel

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | gpg --dearmor -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages buster main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt update \
    && apt install -y gh \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set environment variable for GitHub token

# Download AntAPI wheel using GitHub CLI
ENV ANTAPI_VERSION=1.0.1
RUN gh run download -R STEELISI/ANTapi -n antAPI-$ANTAPI_VERSION-py3-none-any.whl

# Install AntAPI wheel
RUN pip install antAPI-$ANTAPI_VERSION-py3-none-any.whl

WORKDIR /app/

COPY requirements.txt .
#COPY env/gunicorn_conf_dev.py gunicorn_conf.py

RUN \
  pip3 install --no-cache-dir -r requirements.txt \
  && mkdir -p logs

COPY searcch_backend ./searcch_backend
COPY setup.cfg setup.py run.py ./

#ENV FLASK_INSTANCE_CONFIG_FILE=/app/config-development.py
ENV FLASK_APP=run:app

Expose 8080

#CMD ["bash"]
CMD ["gunicorn","--config","gunicorn_conf.py","run:app"]
#CMD ["flask","run","--host=0.0.0.0","--port=80"]
