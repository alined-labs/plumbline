variable "account_id" {
  description = "The Cloudflare account that owns the zone and the Pages project."
  type        = string
}

variable "zone_id" {
  description = "The zone of the domain (alinedlabs.co today)."
  type        = string
}

# The three below come from deploy/prod.env, the one place the domain is set.
variable "web_host" {
  description = "WEB_HOST: the static site on Cloudflare Pages."
  type        = string
}

variable "api_host" {
  description = "API_HOST: the API, through the tunnel to MX3."
  type        = string
}

variable "tunnel_id" {
  description = "TUNNEL_ID: the locally managed tunnel `cloudflared tunnel create` made."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", var.tunnel_id)) && var.tunnel_id != "00000000-0000-0000-0000-000000000000"
    error_message = "Set TUNNEL_ID in deploy/prod.env to the tunnel's UUID first."
  }
}

variable "pages_project" {
  description = "The Pages project deploy.yml uploads to."
  type        = string
  default     = "plumbline"
}
