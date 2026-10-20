terraform {
  required_version = ">= 1.16"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }

  # The state lives outside the repository, on MX3 (infra/cloudflare/tf passes the path at
  # init): it holds account and zone ids, and the repository's .gitignore is frozen.
  backend "local" {}
}

# The token comes from CLOUDFLARE_API_TOKEN, never from a file here.
provider "cloudflare" {}
