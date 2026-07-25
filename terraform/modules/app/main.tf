/**
 * The DocuChat release.
 *
 * The chart lives in this repository rather than a chart museum, so Terraform
 * installs it from a local path. Image references and autoscaling bounds are
 * passed as `set` values, which keeps a promotion (new tag) a one-variable
 * change instead of a values.yaml edit.
 */

locals {
  api_repository = split(":", var.api_image)[0]
  api_tag        = split(":", var.api_image)[1]
  web_repository = split(":", var.web_image)[0]
  web_tag        = split(":", var.web_image)[1]
}

resource "helm_release" "docuchat" {
  name             = var.release_name
  chart            = var.chart_path
  namespace        = var.namespace
  create_namespace = true

  values = [file(var.values_file)]

  set {
    name  = "api.image.repository"
    value = local.api_repository
  }
  set {
    name  = "api.image.tag"
    value = local.api_tag
  }
  set {
    name  = "web.image.repository"
    value = local.web_repository
  }
  set {
    name  = "web.image.tag"
    value = local.web_tag
  }
  set {
    name  = "ingress.host"
    value = var.app_host
  }
  set {
    name  = "api.autoscaling.minReplicas"
    value = var.api_min_replicas
  }
  set {
    name  = "api.autoscaling.maxReplicas"
    value = var.api_max_replicas
  }

  # Wait for every object to report ready, so `terraform apply` finishing means
  # the application is actually serving — not merely submitted to the API server.
  wait          = true
  wait_for_jobs = true
  timeout       = 600

  # Roll back automatically if an upgrade never becomes healthy; a portfolio
  # cluster should demonstrate the same safety net a production one needs.
  atomic          = true
  cleanup_on_fail = true
}
