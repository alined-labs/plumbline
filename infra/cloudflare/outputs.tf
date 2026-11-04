output "api_url" {
  value = "https://${cloudflare_dns_record.api.name}"
}

output "web_url" {
  value = "https://${cloudflare_pages_domain.web.name}"
}
