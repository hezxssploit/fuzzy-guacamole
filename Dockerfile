FROM kalilinux/kali-rolling

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    sudo curl wget git python3 python3-pip python3-venv build-essential \
    libffi-dev libssl-dev perl \
    nmap sqlmap nikto dirb hydra john hashcat \
    whois dnsutils netcat-traditional tcpdump traceroute \
    unzip zip jq openssh-client vim tmux \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY agent.py server.py ./
COPY static/ static/
COPY scripts/ scripts/
RUN chmod +x scripts/*.sh && mkdir -p /workspace/agent_home

ENV AGENT_WORKDIR=/workspace/agent_home

EXPOSE 8000 6080

CMD ["python3", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
