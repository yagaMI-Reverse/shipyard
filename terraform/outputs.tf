output "cluster_name" {
  description = "Name of the kind cluster."
  value       = module.cluster.cluster_name
}

output "kubeconfig_path" {
  description = "kubeconfig for kubectl/helm against this cluster."
  value       = module.cluster.kubeconfig_path
}

output "app_url" {
  description = "Where the deployed application answers."
  value       = "http://${var.app_host}:${var.ingress_http_port}/"
}

output "api_health_url" {
  description = "Liveness endpoint through the Ingress — used by the zero-downtime probe."
  value       = "http://${var.app_host}:${var.ingress_http_port}/api/healthz"
}

output "kubectl_context" {
  description = "Context name kind registers."
  value       = "kind-${module.cluster.cluster_name}"
}
