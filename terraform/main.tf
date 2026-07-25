/**
 * ShipYard — the whole environment as code.
 *
 *   module.cluster   a kind cluster (control-plane + workers, ingress ports)
 *   module.platform  cluster add-ons: ingress-nginx and metrics-server
 *   module.app       the DocuChat Helm release
 *
 * Apply order is enforced with depends_on rather than left to chance: the
 * add-ons need the API server, and the app needs an IngressClass and the
 * metrics API the HPA reads from.
 */

module "cluster" {
  source = "./modules/cluster"

  cluster_name       = var.cluster_name
  kubeconfig_path    = var.kubeconfig_path
  worker_count       = var.worker_count
  ingress_http_port  = var.ingress_http_port
  ingress_https_port = var.ingress_https_port
}

# Both providers talk to the cluster module's kubeconfig. Terraform evaluates
# provider configuration before applying resources, which is why the cluster is
# created in its own targeted apply first (see scripts/up.ps1 and the README).
provider "helm" {
  kubernetes {
    config_path = module.cluster.kubeconfig_path
  }
}

provider "kubernetes" {
  config_path = module.cluster.kubeconfig_path
}

module "platform" {
  source = "./modules/platform"

  depends_on = [module.cluster]
}

module "app" {
  source = "./modules/app"

  chart_path       = "${path.module}/../charts/docuchat"
  values_file      = "${path.module}/../charts/docuchat/values-local.yaml"
  release_name     = "shipyard"
  namespace        = "docuchat"
  app_host         = var.app_host
  api_image        = var.api_image
  web_image        = var.web_image
  api_min_replicas = var.api_min_replicas
  api_max_replicas = var.api_max_replicas

  depends_on = [module.platform]
}
