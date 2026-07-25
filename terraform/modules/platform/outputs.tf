output "ingress_class" {
  description = "IngressClass name the application chart should reference."
  value       = "nginx"
}

output "ingress_namespace" {
  description = "Namespace the ingress controller runs in."
  value       = helm_release.ingress_nginx.namespace
}

output "metrics_server_ready" {
  description = "Marker other modules can depend on to order after metrics-server."
  value       = helm_release.metrics_server.status
}
