# Cloudflare for Plumbline (Lane P, P7b): the two hostnames, the Pages project and its
# domain, and the edge's rate limit. Wednesday's dashboard and CLI steps created them;
# `infra/cloudflare/tf import` adopts them, and from then on this file is the record.
#
# The tunnel itself is not managed here: a locally managed tunnel's secret would sit in
# the state in plain text. It is created once with `cloudflared tunnel create` and only
# referenced by its id.

locals {
  # The routes that start work for a model or the embedder (deploy/cloudflare/rate-limit.md).
  limited_paths = ["/api/ask", "/api/check-lease", "/api/law/check-clause", "/api/law/search"]
}

resource "cloudflare_dns_record" "api" {
  zone_id = var.zone_id
  name    = var.api_host
  type    = "CNAME"
  content = "${var.tunnel_id}.cfargotunnel.com"
  proxied = true
  ttl     = 1 # automatic, as for every proxied record
  comment = "Plumbline API, through the tunnel to MX3"
}

resource "cloudflare_pages_project" "web" {
  account_id        = var.account_id
  name              = var.pages_project
  production_branch = "main" # direct upload from deploy.yml: no source, no build here
}

resource "cloudflare_pages_domain" "web" {
  account_id   = var.account_id
  project_name = cloudflare_pages_project.web.name
  name         = var.web_host
}

resource "cloudflare_dns_record" "web" {
  zone_id = var.zone_id
  name    = var.web_host
  type    = "CNAME"
  content = "${cloudflare_pages_project.web.name}.pages.dev"
  proxied = true
  ttl     = 1
  comment = "Plumbline web, on Cloudflare Pages"
}

# The Free plan allows one rate-limiting rule: a path-only expression, counted per address
# (and data centre) over 10 seconds, blocking for 10 seconds.
resource "cloudflare_ruleset" "rate_limit" {
  zone_id = var.zone_id
  name    = "default"
  kind    = "zone"
  phase   = "http_ratelimit"

  rules = [{
    description = "plumbline: model routes"
    action      = "block"
    expression  = join(" or ", [for path in local.limited_paths : "(http.request.uri.path eq \"${path}\")"])
    ratelimit = {
      characteristics     = ["ip.src", "cf.colo.id"]
      period              = 10
      requests_per_period = 5
      mitigation_timeout  = 10
    }
  }]
}
