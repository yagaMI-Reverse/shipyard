terraform {
  required_version = ">= 1.6.0"

  required_providers {
    kind = {
      source  = "tehcyx/kind"
      version = "~> 0.9"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.17"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.35"
    }
  }

  # Local state, which is the right default for a disposable local cluster.
  # See README "State: moving this to a remote backend" for the S3/GCS version.
  backend "local" {
    path = "terraform.tfstate"
  }
}
