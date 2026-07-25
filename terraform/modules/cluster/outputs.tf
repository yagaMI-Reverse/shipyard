output "cluster_name" {
  description = "Name of the created cluster."
  value       = kind_cluster.this.name
}

output "kubeconfig_path" {
  description = "Absolute path to the generated kubeconfig."
  value       = kind_cluster.this.kubeconfig_path
}

output "endpoint" {
  description = "API server endpoint."
  value       = kind_cluster.this.endpoint
}
