#!/usr/bin/env bash
# Preflight for the server machine (Lane P): can this machine run Plumbline in production?
# Run it with bash (not zsh) as the user that runs Docker, before the first deploy and
# after any change to the machine. It only reads; it changes nothing:
#
#   bash deploy/preflight.sh
#
# Every check prints one line starting with ok, WARN or FAIL, so nothing passes silently.
# Exit status: 0 when nothing failed (warnings allowed), 1 when a check failed, 2 when the
# script itself broke or was misused.
set -Eeuo pipefail
trap 'printf "preflight: stopped by an error at line %d\n" "$LINENO" >&2; exit 2' ERR

readonly GIB=1073741824
# The model servers hold about 5 GB of weights and warm up with about 1 GB each (with
# --max-batch-tokens 4096); Postgres, Redis and the API take about 2 GB more.
readonly MEMORY_FAIL_GIB=11 MEMORY_WARN_GIB=15
# Images, model weights, the database and logs, all under Docker's root directory.
readonly DISK_FAIL_GIB=10 DISK_WARN_GIB=25
# deploy/api/Dockerfile's HEALTHCHECK uses --start-interval, new in Docker Engine 25.
readonly DOCKER_MIN_MAJOR=25
# cloudflared dials both regions on 7844: UDP for QUIC, TCP for the HTTP/2 fallback.
readonly TUNNEL_HOSTS=(region1.v2.argotunnel.com region2.v2.argotunnel.com)
readonly TUNNEL_PORT=7844

oks=0 warns=0 fails=0
ok() { printf 'ok    %s\n' "$*"; oks=$((oks + 1)); }
warn() { printf 'WARN  %s\n' "$*"; warns=$((warns + 1)); }
fail() { printf 'FAIL  %s\n' "$*"; fails=$((fails + 1)); }
have() { command -v "$1" >/dev/null 2>&1; }
gib() { awk -v b="$1" 'BEGIN { printf "%.1f", b / 1073741824 }'; }
# "1 warning", "2 warnings": a count and its noun, plural unless the count is one.
count() { if (($1 == 1)); then printf '%d %s' "$1" "$2"; else printf '%d %ss' "$1" "$2"; fi; }
# Opens a TCP connection to host $1, port $2 with bash's /dev/tcp, giving up after 5 s.
tcp_open() {
  # shellcheck disable=SC2016 # $1 and $2 are expanded by the inner bash, on purpose
  timeout 5 bash -c 'exec 3<>"/dev/tcp/$1/$2"' _ "$1" "$2" 2>/dev/null
}

check_system() {
  if [[ $(uname -s) == Linux ]] && have systemctl; then
    ok "Linux $(uname -r) with systemd"
  else
    fail "needs Linux with systemd: Docker and cloudflared run as systemd services"
  fi
}

check_memory() {
  if [[ ! -r /proc/meminfo ]]; then
    fail "cannot read /proc/meminfo"
    return
  fi
  local kib bytes
  kib=$(awk '/^MemTotal:/ { print $2 }' /proc/meminfo)
  bytes=$((kib * 1024))
  if ((bytes < MEMORY_FAIL_GIB * GIB)); then
    fail "memory $(gib "$bytes") GiB: the stack needs about 10 (the model servers alone hold about 5)"
  elif ((bytes < MEMORY_WARN_GIB * GIB)); then
    warn "memory $(gib "$bytes") GiB: enough for the stack, with little to spare"
  else
    ok "memory $(gib "$bytes") GiB"
  fi
}

check_disk() {
  local dir=$1 avail
  if [[ -z $dir || ! -d $dir ]]; then
    fail "Docker reports no root directory to check free space on"
    return
  fi
  avail=$(df --output=avail -B1 "$dir" | tail -n 1 | tr -d ' ')
  if ((avail < DISK_FAIL_GIB * GIB)); then
    fail "$(gib "$avail") GiB free under $dir: images, model weights and the database take about 10"
  elif ((avail < DISK_WARN_GIB * GIB)); then
    warn "$(gib "$avail") GiB free under $dir: little room for logs and growth"
  else
    ok "$(gib "$avail") GiB free under $dir"
  fi
}

# Docker writes its own iptables rules ahead of the host firewall, so a port published on
# 0.0.0.0 is reachable from the network whatever ufw says. Only loopback bindings are safe.
check_published_ports() {
  local name ports exposed found=0
  while IFS=$'\t' read -r name ports; do
    exposed=$(tr ',' '\n' <<<"$ports" | grep -- '->' | grep -vE '^ *(127\.[0-9.]+|\[::1\]):' |
      tr -d ' ' | paste -sd ' ' -) || true
    if [[ -n $exposed ]]; then
      fail "container $name publishes $exposed beyond loopback: bind it to 127.0.0.1 or drop the port"
      found=1
    fi
  done < <(docker ps --format '{{.Names}}{{"\t"}}{{.Ports}}')
  ((found)) || ok "no running container publishes a port beyond loopback"
}

check_docker() {
  if ! have docker; then
    fail "Docker is not installed"
    return
  fi
  local version compose
  if ! version=$(docker version --format '{{.Server.Version}}' 2>/dev/null); then
    fail "the Docker daemon does not answer $(id -un): is it running, and is $(id -un) in the docker group?"
    return
  fi
  if [[ ${version%%.*} =~ ^[0-9]+$ ]] && ((${version%%.*} >= DOCKER_MIN_MAJOR)); then
    ok "Docker Engine $version"
  else
    fail "Docker Engine $version: needs $DOCKER_MIN_MAJOR or newer for the API image's healthcheck"
  fi
  if compose=$(docker compose version --short 2>/dev/null); then
    ok "Docker Compose $compose"
  else
    fail "the Docker Compose v2 plugin (docker compose) is missing"
  fi
  if [[ $(systemctl is-enabled docker.service 2>/dev/null) == enabled ]]; then
    ok "docker.service starts at boot"
  else
    fail "docker.service does not start at boot (sudo systemctl enable docker)"
  fi
  check_disk "$(docker info --format '{{.DockerRootDir}}' 2>/dev/null)"
  check_published_ports
}

check_listeners() {
  if ! have ss; then
    warn "ss is missing: listening sockets not checked"
    return
  fi
  local open others
  # Local addresses of TCP listeners, without loopback (127.0.0.0/8, ::1, the stub resolver).
  open=$(ss -Hltn | awk '{ print $4 }' | grep -vE '^(127\.|\[::1\]|\[::ffff:127\.)' |
    sort -u | paste -sd ' ' -) || true
  others=$(tr ' ' '\n' <<<"$open" | grep -vE ':22$' | paste -sd ' ' -) || true
  if [[ -z $open ]]; then
    ok "nothing listens beyond loopback"
  elif [[ -z $others ]]; then
    ok "only SSH listens beyond loopback ($open); the router must forward no port here"
  else
    warn "listening beyond loopback: $others; the public reaches the stack only through the tunnel, so the router must forward no port here"
  fi
}

check_clock() {
  if have timedatectl &&
    [[ $(timedatectl show --property=NTPSynchronized --value 2>/dev/null) == yes ]]; then
    ok "the clock is synchronized (NTP)"
  else
    fail "the clock is not synchronized: quotas and spend counters reset at UTC midnight, and TLS needs the right time"
  fi
}

check_updates() {
  if ! have apt-config; then
    warn "not Debian-based: automatic security updates not checked"
    return
  fi
  local config
  config=$(apt-config dump 2>/dev/null) || true
  if grep -qF 'APT::Periodic::Unattended-Upgrade "1";' <<<"$config"; then
    ok "security updates install automatically (unattended-upgrades)"
  else
    warn "security updates do not install automatically (sudo apt install unattended-upgrades)"
  fi
}

# The tunnel itself runs in production Compose (deploy/compose.prod.yaml); the host needs
# the cloudflared CLI only once, for `tunnel login` and `tunnel create`.
check_cloudflared() {
  if have cloudflared; then
    local version
    version=$(cloudflared --version 2>&1) || true
    ok "${version%%$'\n'*} (the CLI, for tunnel login and create)"
  else
    warn "the cloudflared CLI is not installed: it is needed once, to log in and create the tunnel (docs/runbook.md)"
  fi
}

check_tunnel_reach() {
  local host
  for host in "${TUNNEL_HOSTS[@]}"; do
    if ! getent ahosts "$host" >/dev/null; then
      fail "cannot resolve $host, which the tunnel dials"
    elif tcp_open "$host" "$TUNNEL_PORT"; then
      ok "outbound TCP $TUNNEL_PORT to $host"
    else
      warn "no outbound TCP $TUNNEL_PORT to $host: the tunnel can still use QUIC on UDP $TUNNEL_PORT, which this script cannot test"
    fi
  done
}

# The production secrets (deploy/secrets-init.sh): each one root-owned, mode 0640, and in
# the group of the one container user that reads it. Only metadata is read, never content.
check_secrets() {
  local name group meta
  for name in db_password:999 api.env:10001 tunnel.json:65532; do
    group=${name#*:} name=/etc/plumbline/${name%%:*}
    if [[ ! -e $name ]]; then
      warn "$name does not exist yet (sudo bash deploy/secrets-init.sh)"
    elif meta=$(stat -c '%u:%g %a' "$name") && [[ $meta == "0:$group 640" ]]; then
      ok "$name is root:$group, mode 0640"
    else
      fail "$name is $meta (uid:gid mode): it must be 0:$group 640 so only its container reads it"
    fi
  done
}

main() {
  if (($#)); then
    printf 'usage: bash deploy/preflight.sh\n' >&2
    exit 2
  fi
  check_system
  check_memory
  check_docker
  check_listeners
  check_clock
  check_updates
  check_cloudflared
  check_tunnel_reach
  check_secrets
  printf 'preflight: %d ok, %s, %s\n' "$oks" "$(count "$warns" warning)" "$(count "$fails" failure)"
  if ((fails)); then
    exit 1
  fi
}

main "$@"
